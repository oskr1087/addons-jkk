from odoo import fields, models, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    aps_parent_production_id = fields.Many2one(
        'mrp.production',
        string='OF padre APS',
        readonly=True,
        copy=False,
        index=True,
        ondelete='set null',
        help=(
            'Orden de fabricación APS que consume directamente el producto '
            'fabricado por esta OF.'
        ),
    )


class PlanningPlan(models.Model):
    _inherit = 'mrp.planning.plan'

    def _refresh_component_sourcing(self):
        """Keep every manufacturable APS node classified as Manufacture.

        The base sourcing engine historically used the presence of exploded
        child rows as the signal that a component was manufacturable.  That is
        not sufficient: a product can have a valid normal BoM even when its
        frozen node currently has no active children.  In that situation the
        node was classified as Purchase and Fabricar silently skipped the
        corresponding sub-MO.

        After the normal sourcing pass, convert only uncovered purchase
        shortages that have a valid normal manufacturing BoM.  The correction
        is done per APS component node, never by product, so the same product
        can legitimately appear several times in different branches of the
        manufacturing tree and receive a different MO for each requirement.
        """
        components = super()._refresh_component_sourcing()

        from ..services.odoo19_compat import find_bom

        for plan in self:
            if plan.plan_type != 'manufacturing':
                continue

            candidates = plan.production_component_ids.filtered(
                lambda component:
                    component.include_in_mo
                    and component.product_id
                    and component.effective_required_qty > 1e-9
                    and component.to_purchase_qty > 1e-9
                    and not component.is_subcontracted
            )

            for component in candidates:
                warehouse = (
                    component.planning_line_id.target_warehouse_id
                    or plan.warehouse_ids[:1]
                )
                picking_type = warehouse.manu_type_id if warehouse else False
                bom = find_bom(
                    self.env,
                    component.product_id,
                    company_id=plan.company_id.id,
                    picking_type_id=picking_type.id if picking_type else False,
                )
                if not bom or getattr(bom, 'type', 'normal') != 'normal':
                    continue

                qty = component.to_purchase_qty
                resolution = (
                    'move_manufacture'
                    if component.external_move_suggested_qty > 1e-9
                    else 'manufacture'
                )
                component.with_context(
                    aps_skip_subtree_rebuild=True,
                    aps_skip_sourcing_refresh=True,
                ).sudo().write({
                    'to_manufacture_qty': qty,
                    'to_purchase_qty': 0.0,
                    'supply_resolution': resolution,
                })

        return components

    def _aps_link_manufacturing_tree(self):
        """Link every generated component MO to its exact APS parent node.

        Links are based on ``parent_line_id`` / ``aps_planning_component_id``.
        Product equality is intentionally not used because the same product can
        appear more than once in the same manufacturing tree with different
        quantities and parents.
        """
        self.ensure_one()

        components = self.production_component_ids.filtered(
            lambda component: component.generated_production_id
        ).sorted(key=lambda component: (component.level, component.sequence, component.id))

        for component in components:
            child_mo = component.generated_production_id
            if component.parent_line_id:
                parent_mo = component.parent_line_id.generated_production_id
            else:
                parent_mo = component.planning_line_id.created_production_id

            if not parent_mo or parent_mo == child_mo:
                continue

            if 'aps_parent_production_id' in child_mo._fields:
                child_mo.sudo().write({
                    'aps_parent_production_id': parent_mo.id,
                })

            parent_moves = parent_mo.move_raw_ids.filtered(
                lambda move:
                    move.state != 'cancel'
                    and getattr(move, 'aps_planning_component_id', False) == component
            )
            child_finished_moves = child_mo.move_finished_ids.filtered(
                lambda move:
                    move.state != 'cancel'
                    and move.product_id == child_mo.product_id
            )

            if not parent_moves or not child_finished_moves:
                continue

            for parent_move in parent_moves:
                missing_origins = child_finished_moves - parent_move.move_orig_ids
                if missing_origins:
                    parent_move.sudo().write({
                        'move_orig_ids': [(4, move.id) for move in missing_origins],
                    })

        return True

    def _aps_validate_complete_manufacturing_tree(self):
        """Never allow Fabricar to finish with a required sub-MO missing."""
        self.ensure_one()
        missing = self.production_component_ids.filtered(
            lambda component:
                component.include_in_mo
                and component.to_manufacture_qty > 1e-9
                and not component.generated_production_id
        )
        if missing:
            details = '\n'.join(
                '- Nivel %(level)s | %(path)s | %(product)s | %(qty).4f %(uom)s' % {
                    'level': component.level,
                    'path': component.path or component.product_id.display_name,
                    'product': component.product_id.display_name,
                    'qty': component.to_manufacture_qty,
                    'uom': component.product_uom_id.display_name,
                }
                for component in missing.sorted(
                    key=lambda row: (row.level, row.sequence, row.id)
                )
            )
            raise UserError(_(
                'APS detectó componentes fabricables sin orden de fabricación. '
                'No se completará el proceso Fabricar hasta generar toda la '
                'jerarquía:\n%s'
            ) % details)
        return True

    def action_create_manufacturing(self):
        result = super().action_create_manufacturing()
        self._aps_validate_complete_manufacturing_tree()
        self._aps_link_manufacturing_tree()
        return result
