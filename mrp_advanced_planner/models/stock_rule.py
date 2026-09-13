from odoo import models


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _aps_procurement_context(self, procurement):
        """Return APS traceability carried by the downstream raw move."""
        move_dest_ids = procurement.values.get('move_dest_ids')
        if not move_dest_ids:
            return False

        moves = move_dest_ids.exists()
        if not moves:
            return False

        # The first native sub-MO comes from a raw move of the APS root MO.
        # Deeper sub-MOs come from raw moves of an already enriched native
        # child MO. Both paths are handled here.
        component = moves.mapped('aps_planning_component_id')[:1]
        parent_mo = moves.mapped('raw_material_production_id')[:1]
        plan = (
            parent_mo.advanced_plan_id
            if parent_mo and parent_mo.advanced_plan_id
            else moves.mapped('planning_plan_line_id.plan_id')[:1]
        )
        planning_line = (
            parent_mo.planning_plan_line_id
            if parent_mo and parent_mo.planning_plan_line_id
            else moves.mapped('planning_plan_line_id')[:1]
        )
        sale_line = (
            parent_mo.planning_sale_line_id
            if parent_mo and parent_mo.planning_sale_line_id
            else False
        )
        if not plan or not planning_line:
            return False

        return {
            'plan': plan,
            'planning_line': planning_line,
            'component': component,
            'parent_mo': parent_mo,
            'sale_line': sale_line,
            'moves': moves,
        }

    def _aps_find_created_native_submos(self, downstream_moves):
        """Locate manufacturing orders whose finished move feeds these moves."""
        if not downstream_moves:
            return self.env['mrp.production']
        return self.env['mrp.production'].sudo().search([
            ('move_finished_ids.move_dest_ids', 'in', downstream_moves.ids),
            ('state', '!=', 'cancel'),
        ])

    def _aps_enrich_and_confirm_native_submos(self, procurements):
        """Attach the frozen APS subtree to Odoo-created sub-MOs.

        Odoo remains responsible for creating the sub-MO through the native
        manufacture rule. APS only restores its traceability/snapshot before
        confirmation so the child MO receives its own direct components and
        lot reservations. This also works recursively for deeper sub-MOs.
        """
        for procurement, _rule in procurements:
            ctx = self._aps_procurement_context(procurement)
            if not ctx:
                continue

            productions = self._aps_find_created_native_submos(ctx['moves'])
            for mo in productions:
                vals = {
                    'advanced_plan_id': ctx['plan'].id,
                    'planning_plan_line_id': ctx['planning_line'].id,
                    'aps_parent_production_id': (
                        ctx['parent_mo'].id if ctx['parent_mo'] else False
                    ),
                }
                if ctx['sale_line']:
                    vals['planning_sale_line_id'] = ctx['sale_line'].id

                # Exact APS component that originated this native sub-MO.
                component = ctx['component']
                if component and mo.product_id == component.product_id:
                    vals.update({
                        'aps_component_snapshot': True,
                        'aps_planning_component_id': component.id,
                    })

                mo.write(vals)

                # Persist the reverse link as well. Odoo remains the creator
                # of the native sub-MO; APS only records which engineering
                # component it is executing.
                if (
                    component
                    and mo.product_id == component.product_id
                    and component.generated_production_id != mo
                ):
                    component.with_context(
                        aps_skip_sourcing_refresh=True,
                        aps_skip_change_tracking=True,
                    ).write({
                        'generated_production_id': mo.id,
                    })

                # The native child was created from Odoo's BoM before APS
                # traceability was attached.  While it is still draft, replace
                # those raw moves with the frozen APS direct snapshot so every
                # next-level manufacturing demand carries the exact
                # aps_planning_component_id.  This is what makes recursive
                # submanufacturing deterministic.
                if (
                    component
                    and mo.aps_component_snapshot
                    and mo.state == 'draft'
                ):
                    mo.with_context(
                        skip_compute_move_raw_ids=True
                    )._aps_sync_raw_moves()
                elif mo.aps_component_snapshot:
                    # Recovery path for an already-confirmed native child from
                    # an older module version: keep its moves/reservations and
                    # only restore APS identity.
                    mo._aps_adopt_existing_raw_moves()

                # IMPORTANT OWNERSHIP RULE:
                # The child MO must own its children's APS lot reservations
                # BEFORE action_confirm(). Odoo may try to reserve raw moves
                # during confirmation, and the APS stock.move-line guard runs
                # at that moment. If ownership is corrected only afterwards,
                # confirmation fails first with a false conflict against the
                # parent/root MO.
                direct_components = self.env[
                    'mrp.planning.production.component'
                ]
                if mo.aps_component_snapshot and mo.aps_planning_component_id:
                    direct_components = mo._aps_snapshot_components()
                    child_reservations = direct_components.mapped(
                        'lot_reservation_ids'
                    ).filtered(
                        lambda reservation:
                            reservation.state in ('reserved', 'assigned')
                    )
                    if child_reservations:
                        child_reservations.with_context(
                            aps_allow_locked_lot_reservation_write=True
                        ).write({
                            'production_id': mo.id,
                            'state': 'assigned',
                        })

                # If Odoo created the MTO child in draft (normal in Odoo 19
                # for this chain), confirm it only AFTER the logical ownership
                # above is already correct.
                if mo.state == 'draft':
                    mo.action_confirm()

                # A native child MO may have been created while purchases/lots
                # were still pending. Reserve whatever is physically available
                # now; absence of full material does not prevent the child MO
                # from existing, but action_start/button_mark_done will block
                # actual production until readiness is complete.
                if mo.state not in ('done', 'cancel'):
                    mo.action_assign()

                if direct_components:
                    # Odoo may have physically reserved stock while confirming
                    # the native sub-MO. Synchronize the logical layer against
                    # that same physical reservation.
                    tracked = direct_components.filtered(
                        lambda component:
                            component.product_id.is_storable
                            and component.product_id.tracking != 'none'
                            and component.include_in_mo
                    )
                    if tracked:
                        tracked.with_context(
                            aps_allow_locked_lot_sync=True
                        )._aps_sync_default_lot_reservations()

                    # Re-assert child ownership after synchronization in case a
                    # compatibility path created/updated reservations.
                    direct_components.mapped(
                        'lot_reservation_ids'
                    ).filtered(
                        lambda reservation:
                            reservation.state in ('reserved', 'assigned')
                    ).with_context(
                        aps_allow_locked_lot_reservation_write=True
                    ).write({
                        'production_id': mo.id,
                        'state': 'assigned',
                    })

                    # IMPORTANT:
                    # Do not recompute ComponentSourcingEngine here. The OF and
                    # native sub-OF are execution documents generated FROM the
                    # APS decision. Their own incoming/reserved stock must not
                    # retroactively change "Fabricar/Comprar" into "Cubierto"
                    # or make descendants "No requerido".
                    #
                    # Lot ownership above is operational and may evolve, but
                    # the sourcing decision remains frozen until the user
                    # explicitly presses Recalcular.
                    pass

        return True

    def _run_manufacture(self, procurements):
        """Suppress only sale-origin MTO manufacturing.

        Manufacturing triggered by components of an APS root MO stays native.
        After Odoo creates those sub-MOs, APS enriches and confirms them so
        each subfabrication has its own components, lot ownership and
        traceability.
        """
        if self.env.context.get('aps_hold_sale_mto_manufacturing'):
            return True

        # APS confirms its own MOs with ``skip_compute_move_raw_ids`` so
        # Odoo cannot overwrite the frozen snapshot.  That context MUST NOT
        # leak into Odoo's native manufacture rule: otherwise the child MO is
        # created with its BoM but without raw moves.  Always execute the
        # native rule with the flag explicitly disabled.
        native_rule = self.with_context(skip_compute_move_raw_ids=False)
        result = super(StockRule, native_rule)._run_manufacture(procurements)
        native_rule._aps_enrich_and_confirm_native_submos(procurements)
        return result
