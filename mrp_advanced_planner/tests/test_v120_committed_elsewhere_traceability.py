from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV120CommittedElsewhereTraceability(TransactionCase):

    def test_mo_commitment_recovers_native_sale_move_links(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'sale_extensions.py').read_text()
        method = source.split(
            'def mo_source_sale_lines', 1
        )[1].split('def po_source_sale_lines', 1)[0]
        self.assertIn("finished.move_dest_ids", method)
        self.assertIn("mapped('sale_line_id')", method)

    def test_other_manufacturing_is_payload_but_not_coverage(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'sale_extensions.py').read_text()
        self.assertIn("'other_mos': other_mo_rows", source)
        self.assertIn(
            "'committed_elsewhere_qty': other_mo + other_po",
            source,
        )
        coverage_block = source.split(
            'physical_cover = min(pending, free_qty)', 1
        )[1].split("line.aps_forecast_qty = forecast", 1)[0]
        self.assertNotIn('other_mo', coverage_block)
        self.assertNotIn('other_po', coverage_block)

    def test_popup_lists_committed_documents_as_informative(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'sale_extensions.py').read_text()
        self.assertIn("'document_type': 'mo_other'", source)
        self.assertIn("'document_type': 'po_other'", source)
        self.assertIn("Comprometido a otra venta", source)
