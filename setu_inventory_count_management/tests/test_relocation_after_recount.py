# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestRelocationAfterRecount(TransactionCase):

    def test_stale_relocation_is_closed_after_recount(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/inventory_count_location_flow.py").read_text(encoding="utf-8")
        self.assertIn("Cerrar incidencias obsoletas después de reconteos/consolidaciones", code)
        self.assertIn("snapshot.counted_qty > 0", code)
        self.assertIn('"state": "resolved"', code)
        self.assertIn('"quantity_to_move": 0.0', code)

    def test_pending_metric_uses_current_snapshot(self):
        module = Path(__file__).resolve().parents[1]
        code = (module / "models/inventory_count_location_flow.py").read_text(encoding="utf-8")
        self.assertIn('issue.snapshot_line_id.status == "unexpected"', code)
        self.assertIn("issue.snapshot_line_id.counted_qty > 0", code)
