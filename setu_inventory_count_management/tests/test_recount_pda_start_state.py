# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestRecountPDAStartState(TransactionCase):

    def test_start_uses_current_state_created_not_only_draft_state(self):
        module = Path(__file__).resolve().parents[1]
        code = (
            module / "models/pda_counting.py"
        ).read_text(encoding="utf-8")

        start = code.index("def pda_fast_control")
        end = code.index("def pda_fast_set_observation", start)
        block = code[start:end]

        self.assertIn(
            "if self.current_state == 'Created':",
            block,
        )
        self.assertIn("self.start()", block)

    def test_scan_normalizes_in_progress_created_session(self):
        module = Path(__file__).resolve().parents[1]
        code = (
            module / "models/pda_counting.py"
        ).read_text(encoding="utf-8")

        start = code.index("def pda_fast_scan")
        end = code.index("def pda_fast_finish_location", start)
        block = code[start:end]

        self.assertIn(
            "if self.state == 'In Progress' and self.current_state == 'Created':",
            block,
        )
        self.assertIn("self.start()", block)
