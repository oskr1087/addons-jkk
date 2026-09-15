# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestRecountDoneSessionReadiness(TransactionCase):

    def test_done_session_does_not_false_block_recount_approval(self):
        module = Path(__file__).resolve().parents[1]
        code = (
            module / "models/inventory_count_snapshot.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'open_recount_sessions = recount_sessions.filtered(',
            code,
        )
        self.assertIn(
            'lambda session: session.state != "Done"',
            code,
        )
        self.assertIn(
            'unscanned_recount_lines = open_recount_sessions.mapped(',
            code,
        )

    def test_recount_action_is_named_approve(self):
        module = Path(__file__).resolve().parents[1]
        xml = (
            module / "views/inventory_count_snapshot_views.xml"
        ).read_text(encoding="utf-8")
        self.assertIn('string="Aprobar reconteo"', xml)
