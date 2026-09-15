# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestInternalTransferOdoo19(TransactionCase):

    def test_no_obsolete_stock_move_name_in_location_flow(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/inventory_count_location_flow.py").read_text(encoding="utf-8")
        block = code.split("def _create_internal_transfer", 1)[1].split("def _update_snapshot_after_transfer", 1)[0]
        self.assertNotIn('"name": self.product_id.display_name', block)
        self.assertIn('"description_picking"', block)

    def test_controlled_count_correction_context_exists(self):
        module = Path(__file__).resolve().parents[1]
        flow = (module / "models/inventory_count_location_flow.py").read_text(encoding="utf-8")
        stock = (module / "models/stock_move.py").read_text(encoding="utf-8")
        self.assertIn("setu_inventory_count_correction_count_id", flow)
        self.assertIn("setu_inventory_count_correction_count_id", stock)
        self.assertIn("allowed_correction", stock)
