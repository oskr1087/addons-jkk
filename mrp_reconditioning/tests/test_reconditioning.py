from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestMrpReconditioning(TransactionCase):
    def setUp(self):
        super().setUp()
        self.product = self.env["product.product"].create(
            {"name": "Reconditioned Product", "is_storable": True}
        )
        self.other_product = self.env["product.product"].create(
            {"name": "Other Product", "is_storable": True}
        )

    def test_reconditioning_uses_separate_sequence(self):
        production = self.env["mrp.production"].create(
            {
                "is_reconditioning": True,
                "product_id": self.product.id,
                "product_qty": 1.0,
                "product_uom_id": self.product.uom_id.id,
            }
        )
        self.assertTrue(production.name.startswith("REAC/"))

    def test_original_production_must_match_product(self):
        original = self.env["mrp.production"].create(
            {
                "product_id": self.other_product.id,
                "product_qty": 1.0,
                "product_uom_id": self.other_product.uom_id.id,
            }
        )
        with self.assertRaises(ValidationError):
            self.env["mrp.production"].create(
                {
                    "is_reconditioning": True,
                    "product_id": self.product.id,
                    "product_qty": 1.0,
                    "product_uom_id": self.product.uom_id.id,
                    "original_production_id": original.id,
                }
            )

    def test_reconditioning_cannot_confirm_without_customer_return(self):
        production = self.env["mrp.production"].create(
            {
                "is_reconditioning": True,
                "product_id": self.product.id,
                "product_qty": 1.0,
                "product_uom_id": self.product.uom_id.id,
            }
        )
        with self.assertRaises(UserError):
            production.action_confirm()
