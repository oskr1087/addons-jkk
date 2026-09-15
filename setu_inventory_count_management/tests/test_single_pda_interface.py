# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSinglePDAInterface(TransactionCase):

    def test_only_pda_client_action_is_supported(self):
        module = Path(__file__).resolve().parents[1]

        session_py = (
            module / "models/setu_inventory_count_session.py"
        ).read_text(encoding="utf-8")
        pda_py = (
            module / "models/pda_counting.py"
        ).read_text(encoding="utf-8")
        views = (
            module / "views/setu_inventory_count_session_views.xml"
        ).read_text(encoding="utf-8")
        pda_views = (
            module / "views/pda_counting_views.xml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "'tag': 'setu_inventory_count_management.pda_fast_count'",
            session_py,
        )
        self.assertIn(
            "'tag': 'setu_inventory_count_management.pda_fast_count'",
            pda_py,
        )
        self.assertNotIn(
            "'setu_inventory_count_management.inventory_count_session_mobile_form_view'",
            session_py,
        )
        self.assertIn(
            '<field name="active" eval="False"/>',
            views,
        )
        self.assertIn(
            '<field name="active" eval="False"/>',
            pda_views,
        )
