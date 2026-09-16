from odoo.tests.common import TransactionCase

class TestReconditioning(TransactionCase):
    def test_models(self):
        self.assertTrue(self.env["mrp.reconditioning"])
        self.assertTrue(self.env["mrp.reconditioning.component"])
