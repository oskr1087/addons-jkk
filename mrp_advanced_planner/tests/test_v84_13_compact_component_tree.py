from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV8413CompactComponentTree(TransactionCase):

    def test_tree_uses_compact_columns_and_keeps_actions_wide(self):
        root = Path(__file__).parents[1]
        css = (root / 'static' / 'src' / 'css' / 'planning_component_tree.css').read_text()
        self.assertIn('minmax(190px, auto)', css)
        self.assertIn('justify-content: flex-end', css)
        self.assertNotIn('min-width: 1250px', css)
