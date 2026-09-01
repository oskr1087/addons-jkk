from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV74ComponentModificationValidation(TransactionCase):

    def test_modified_snapshot_does_not_keep_native_bom_line(self):
        """Modified qty must be a manual APS raw move at MO validation time."""
        from ..models import mrp_extensions
        source = Path(mrp_extensions.__file__).read_text()
        self.assertIn(
            "and component.change_type == 'original'",
            source,
        )

    def test_engineering_change_type_is_centralized(self):
        component = self.env['mrp.planning.production.component']
        self.assertTrue(
            hasattr(component, '_aps_engineering_change_type')
        )

    def test_supported_change_types_remain_available(self):
        field = self.env[
            'mrp.planning.production.component'
        ]._fields['change_type']
        selection = field.selection
        if callable(selection):
            selection = selection(self.env)
        values = dict(selection)
        for key in ('original', 'modified', 'replaced', 'manual', 'omitted'):
            self.assertIn(key, values)

    def test_modified_qty_is_intentional_snapshot_change(self):
        # Static regression: modified lines must not be accepted as native
        # engineering lines solely because product/bom still match.
        from ..models import mrp_extensions
        source = Path(mrp_extensions.__file__).read_text()
        block_start = source.index("native_bom_line = (")
        block = source[block_start:block_start + 700]
        self.assertIn("component.change_type == 'original'", block)
        self.assertIn("else self.env['mrp.bom.line']", block)
