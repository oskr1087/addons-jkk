from odoo import api, models


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.depends(
        "raw_material_production_id.qty_producing",
        "raw_material_production_id.qty_produced",
        "raw_material_production_id.product_qty",
        "product_uom_qty",
        "product_uom",
        "unit_factor",
        "bom_line_id",
        "manual_consumption",
    )
    def _compute_should_consume_qty(self):
        """Use a BoM-based target only for automatic production components.

        This prevents a previously modified move demand/unit_factor from being
        scaled a second time. Other stock moves and manual MRP consumption keep
        the standard Odoo computation.
        """
        custom_moves = self.filtered(
            lambda m: m.raw_material_production_id
            and not m.manual_consumption
            and m.raw_material_production_id.qty_producing > 0
        )
        standard_moves = self - custom_moves
        if standard_moves:
            super(StockMove, standard_moves)._compute_should_consume_qty()

        moves_by_production = {}
        for move in custom_moves:
            moves_by_production.setdefault(move.raw_material_production_id, self.env["stock.move"])
            moves_by_production[move.raw_material_production_id] |= move

        for production, moves in moves_by_production.items():
            targets = production._get_raw_consumption_targets()
            for move in moves:
                # Once the MO/raw move is done, "Por consumir" must reflect
                # exactly what was actually consumed.  Odoo may change
                # qty_producing after validation (for instance while preparing
                # a backorder), so recomputing the BoM target at that point can
                # show a stale proportional value (e.g. 65.96 vs 82.45).
                # This is intentionally restricted to raw material production
                # moves; every other stock.move keeps standard Odoo behavior.
                if production.state == "done" or move.state == "done":
                    move.should_consume_qty = move.quantity
                elif move.id in targets:
                    move.should_consume_qty = targets[move.id]
                else:
                    # Safe fallback for custom/generated raw moves that cannot
                    # be mapped back to a BoM line.
                    super(StockMove, move)._compute_should_consume_qty()
