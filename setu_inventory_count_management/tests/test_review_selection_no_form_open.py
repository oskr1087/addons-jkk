# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

@tagged("post_install", "-at_install")
class TestReviewSelectionNoFormOpen(TransactionCase):
    def test_review_list_does_not_open_snapshot_form(self):
        module = Path(__file__).resolve().parents[1]
        xml = (module / "views/inventory_count_snapshot_views.xml").read_text(encoding="utf-8")
        start = xml.index('name="snapshot_to_resolve_line_ids"')
        list_start = xml.index("<list", start)
        list_end = xml.index(">", list_start)
        tag = xml[list_start:list_end + 1]
        self.assertIn('open_form_view="0"', tag)
        self.assertIn('name="review_selected"', xml[start:])
