# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestReviewInlineSelection(TransactionCase):

    def test_review_one2many_is_editable_only_for_selection(self):
        module = Path(__file__).resolve().parents[1]
        xml = (
            module / "views/inventory_count_snapshot_views.xml"
        ).read_text(encoding="utf-8")

        start = xml.index('name="snapshot_to_resolve_line_ids"')
        end = xml.index("</list>", start)
        block = xml[start:end]

        # El x2many no debe estar readonly, o el clic abre el formulario.
        first_tag_end = block.index(">")
        field_tag = block[:first_tag_end + 1]
        self.assertNotIn('readonly="1"', field_tag)

        # La lista debe aceptar edición inline y no abrir formulario.
        self.assertIn('editable="bottom"', block)
        self.assertIn('open_form_view="0"', block)

        # Solo el selector queda operativo.
        self.assertIn(
            'name="review_selected" string="Sel." '
            'readonly="not parent.can_review_actions"',
            block,
        )
        self.assertIn('name="product_id" readonly="1"', block)
        self.assertIn('name="review_decision" string="Decisión" readonly="1"', block)
