from collections import defaultdict

from odoo import fields
from odoo.exceptions import UserError

from .odoo19_compat import find_bom
from .run_cache import PlanningRunCache


class BomExplosionEngine:
    """Explodes Odoo BOMs into traceable planning requirements without creating MRP docs."""

    def __init__(self, plan):
        self.plan = plan
        self.env = plan.env
        self._seen = set()
        self.cache = PlanningRunCache(self.env)
        self._boms = {}

    def _find_bom(self, product):
        key = (product.id, self.plan.company_id.id)
        if key not in self._boms:
            self._boms[key] = find_bom(
                self.env, product, company_id=self.plan.company_id.id
            )
        return self._boms[key]

    def _required_date(self, parent_date, bom):
        if not parent_date:
            return fields.Datetime.now()
        days = getattr(bom, "days_to_prepare_mo", 0.0) or 0.0
        return fields.Datetime.subtract(parent_date, days=days)

    def _explode_node(self, product, quantity, date_required, level=0, parent=None):
        if quantity <= 0:
            return
        key = (product.id, level, parent.id if parent else False, date_required)
        if key in self._seen:
            return
        self._seen.add(key)
        bom = self._find_bom(product)
        if not bom:
            return
        factor = quantity / (bom.product_qty or 1.0)
        for bom_line in bom.bom_line_ids:
            component = bom_line.product_id
            component_qty = bom_line.product_uom_id._compute_quantity(
                bom_line.product_qty * factor,
                component.uom_id,
            )
            if len(self._seen) >= self.plan.max_requirements:
                raise UserError(
                    "The requirement safety limit was reached for this planning run."
                )
            requirement = self.env["mrp.planning.requirement"].create(
                {
                    "plan_id": self.plan.id,
                    "parent_id": parent.id if parent else False,
                    "product_id": component.id,
                    "bom_id": bom.id,
                    "bom_line_id": bom_line.id,
                    "level": level + 1,
                    "required_qty": component_qty,
                    "date_required": self._required_date(date_required, bom),
                    "supply_type": "blocked",
                }
            )
            child_bom = self._find_bom(component)
            if child_bom:
                self._explode_node(
                    component,
                    component_qty,
                    requirement.date_required,
                    level + 1,
                    requirement,
                )

    def run(self):
        self.plan.requirement_ids.unlink()
        for line in self.plan.line_ids.filtered(
            lambda item: item.product_id and item.net_requirement_qty > 0
        ):
            self._explode_node(
                line.product_id, line.net_requirement_qty, line.date_required
            )
        return self.plan.requirement_ids
