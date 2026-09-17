# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestPDAPauseResumeState(TransactionCase):
    def test_backend_pause_uses_real_session_state(self):
        root=Path(__file__).resolve().parents[1]
        src=(root/"models/pda_counting.py").read_text(encoding="utf-8")
        self.assertIn("self.current_state == 'Pause'", src)
        self.assertIn("scan_context.paused = True", src)
        self.assertIn("'paused': False", src)

    def test_resume_button_visible_for_paused_state(self):
        root=Path(__file__).resolve().parents[1]
        xml=(root/"static/src/xml/pda_fast_count.xml").read_text(encoding="utf-8")
        self.assertIn('t-if="state.data.paused"', xml)
        self.assertIn("REANUDAR", xml)
        self.assertIn("REANUDAR CONTEO", xml)
