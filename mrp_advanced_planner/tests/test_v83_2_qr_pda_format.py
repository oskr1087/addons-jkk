from odoo.tests.common import TransactionCase


class TestV832QrPdaFormat(TransactionCase):

    def test_payload_order_matches_inventory_count_pda(self):
        product = self.env['product.product'].create({
            'name': 'Producto QR PDA',
            'default_code': 'PROD-001',
            'is_storable': True,
            'tracking': 'lot',
        })
        lot = self.env['stock.lot'].create({
            'name': 'LOT-001',
            'product_id': product.id,
        })
        payload = lot._aps_pda_qr_payload()
        self.assertEqual(payload, 'PROD-001/LOT-001/0.00')
