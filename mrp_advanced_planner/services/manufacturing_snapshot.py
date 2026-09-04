from odoo.exceptions import UserError

from .bom_batch import BatchBomGraph


class ManufacturingSnapshotBuilder:
    """Freeze the engineering structure used by an APS manufacturing line."""

    MAX_DEPTH = 30

    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env
        self.graph = BatchBomGraph(self.env, plan.company_id)

    def _qty(self, bom, bom_line, parent, parent_qty):
        parent_bom_uom = parent.uom_id._compute_quantity(parent_qty, bom.product_uom_id)
        factor = parent_bom_uom / (bom.product_qty or 1.0)
        return bom_line.product_uom_id._compute_quantity(
            bom_line.product_qty * factor, bom_line.product_id.uom_id
        )

    def _subtree_vals(self, planning_line, product, qty, parent_id=False,
                      level=0, path=None, visiting=None):
        self.graph.preload(product)
        vals = []

        def walk(current_product, current_qty, current_parent_id,
                 current_level, current_path, current_visiting):
            if current_level > self.MAX_DEPTH:
                raise UserError(
                    'La explosión de fabricación superó %s niveles.'
                    % self.MAX_DEPTH
                )
            visiting = set(current_visiting or ())
            if current_product.id in visiting:
                raise UserError(
                    'Se detectó una referencia circular de LdM en %s.'
                    % current_product.display_name
                )
            visiting.add(current_product.id)
            bom = self.graph.bom(current_product)
            if not bom:
                return
            for bl in bom.bom_line_ids:
                component = bl.product_id
                cqty = self._qty(bom, bl, current_product, current_qty)
                if cqty <= 1e-9:
                    continue
                cpath = list(current_path) + [component.display_name]
                row = {
                    'plan_id': self.plan.id,
                    'planning_line_id': planning_line.id,
                    'parent_line_id': current_parent_id or False,
                    'root_product_id': planning_line.product_id.id,
                    'product_id': component.id,
                    'original_product_id': component.id,
                    'product_uom_id': component.uom_id.id,
                    'original_qty': cqty,
                    'planned_qty': cqty,
                    'level': current_level + 1,
                    'sequence': bl.sequence,
                    'path': ' → '.join(cpath),
                    'source_bom_id': bom.id,
                    'source_bom_line_id': bl.id,
                    'change_type': 'original',
                    'include_in_mo': True,
                }
                vals.append((row, component, cqty, cpath, visiting))
        walk(product, qty, parent_id, level, path or [product.display_name], visiting)
        return vals

    def rebuild_component_subtree(self, component):
        """Refresh descendants after replacing a component product."""
        Component = self.env['mrp.planning.production.component']
        component.child_line_ids.unlink()
        self.graph = BatchBomGraph(self.env, self.plan.company_id)
        self.graph.preload(component.product_id)

        def create_children(parent, product, qty, level, path, visiting=None):
            visiting = set(visiting or ())
            if product.id in visiting:
                raise UserError(
                    'Se detectó una referencia circular de LdM en %s.'
                    % product.display_name
                )
            visiting.add(product.id)
            bom = self.graph.bom(product)
            if not bom:
                return Component
            created = Component
            for bl in bom.bom_line_ids:
                child_product = bl.product_id
                child_qty = self._qty(bom, bl, product, qty)
                if child_qty <= 1e-9:
                    continue
                child_path = list(path) + [child_product.display_name]
                child = Component.with_context(
                    aps_skip_subtree_rebuild=True,
                    aps_skip_sourcing_refresh=True,
                ).create({
                    'plan_id': self.plan.id,
                    'planning_line_id': component.planning_line_id.id,
                    'parent_line_id': parent.id,
                    'root_product_id': component.root_product_id.id,
                    'product_id': child_product.id,
                    'original_product_id': child_product.id,
                    'product_uom_id': child_product.uom_id.id,
                    'original_qty': child_qty,
                    'planned_qty': child_qty,
                    'level': level + 1,
                    'sequence': bl.sequence,
                    'path': ' → '.join(child_path),
                    'source_bom_id': bom.id,
                    'source_bom_line_id': bl.id,
                    'change_type': 'original',
                    'include_in_mo': True,
                })
                created |= child
                created |= create_children(
                    child, child_product, child_qty,
                    level + 1, child_path, visiting
                )
            return created

        return create_children(
            component,
            component.product_id,
            component.planned_qty,
            component.level,
            (component.path or component.product_id.display_name).split(' → '),
        )

    def build(self, planning_lines):
        Component = self.env['mrp.planning.production.component']
        Component.with_context(
            aps_skip_sourcing_refresh=True
        ).search([
            ('planning_line_id', 'in', planning_lines.ids)
        ]).unlink()

        self.graph.preload(planning_lines.mapped('product_id'))
        vals = []

        def walk(
            line, product, qty, parent_tmp=None, level=0, path=None,
            visiting=None, bom_override=False,
        ):
            if level > self.MAX_DEPTH:
                raise UserError(
                    'La explosión de fabricación superó %s niveles.'
                    % self.MAX_DEPTH
                )
            visiting = set(visiting or ())
            visit_key = (
                product.id,
                bom_override.id if bom_override else False,
            )
            if visit_key in visiting:
                raise UserError(
                    'Se detectó una referencia circular de LdM en %s.'
                    % product.display_name
                )
            visiting.add(visit_key)

            bom = bom_override or self.graph.bom(product)
            if not bom:
                return

            base_path = list(path or [line.product_id.display_name])
            for bl in bom.bom_line_ids:
                component = bl.product_id
                cqty = self._qty(bom, bl, product, qty)
                if cqty <= 1e-9:
                    continue

                subcontract_bom = self.graph.subcontract_bom(component)
                is_subcontracted = bool(subcontract_bom)
                token = len(vals)
                cpath = base_path + [component.display_name]

                vals.append({
                    '_token': token,
                    '_parent_token': parent_tmp,
                    'plan_id': self.plan.id,
                    'planning_line_id': line.id,
                    'root_product_id': line.product_id.id,
                    'product_id': component.id,
                    'original_product_id': component.id,
                    'product_uom_id': component.uom_id.id,
                    'original_qty': cqty,
                    'planned_qty': cqty,
                    'level': level + 1,
                    'sequence': bl.sequence,
                    'path': ' → '.join(cpath),
                    'source_bom_id': bom.id,
                    'source_bom_line_id': bl.id,
                    'change_type': 'original',
                    'include_in_mo': True,
                    'is_subcontracted': is_subcontracted,
                    'subcontract_bom_id': (
                        subcontract_bom.id if subcontract_bom else False
                    ),
                })

                # A subcontracted component is visible as one sourcing node.
                # Its subcontract BOM children are displayed for engineering
                # traceability, but ComponentSourcingEngine will assign zero
                # effective demand to those children and purchase the parent.
                if subcontract_bom:
                    walk(
                        line, component, cqty, token, level + 1, cpath,
                        visiting, bom_override=subcontract_bom,
                    )
                elif self.graph.bom(component):
                    walk(
                        line, component, cqty, token, level + 1, cpath,
                        visiting,
                    )

        for line in planning_lines:
            walk(
                line,
                line.product_id,
                line.planner_production_qty,
            )

        created_by_token = {}
        for row in vals:
            token = row.pop('_token')
            parent_token = row.pop('_parent_token')
            if parent_token is not None:
                row['parent_line_id'] = created_by_token[parent_token].id
            created_by_token[token] = Component.with_context(
                aps_skip_sourcing_refresh=True,
                aps_skip_subtree_rebuild=True,
            ).create(row)

        return Component.browse(
            [record.id for record in created_by_token.values()]
        )
