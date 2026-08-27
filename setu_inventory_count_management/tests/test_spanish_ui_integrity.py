# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestSpanishUiIntegrity(TransactionCase):
    """Evita traducir valores técnicos usados por la lógica del módulo."""

    def test_inventory_count_selection_keys_are_stable(self):
        field = self.env["setu.stock.inventory.count"]._fields["state"]
        values = dict(field._description_selection(self.env))
        self.assertIn("Draft", values)
        self.assertIn("In Progress", values)
        self.assertIn("To Be Approved", values)
        self.assertIn("Approved", values)
        self.assertIn("Inventory Adjusted", values)
        self.assertEqual(values["Draft"], "Borrador")

    def test_session_selection_keys_are_stable(self):
        field = self.env["setu.inventory.count.session"]._fields["state"]
        values = dict(field._description_selection(self.env))
        for key in ("Draft", "In Progress", "Submitted", "Done", "Cancel"):
            self.assertIn(key, values)

    def test_draft_view_uses_technical_state_values(self):
        view = self.env.ref("setu_inventory_count_management.setu_stock_inventory_count_form_view")
        arch = view.arch_db
        self.assertIn("state != 'Draft'", arch)
        self.assertNotIn("state != 'Borrador'", arch)
        self.assertNotIn("state != 'En progreso'", arch)
        self.assertNotIn("state != 'Por aprobar'", arch)
