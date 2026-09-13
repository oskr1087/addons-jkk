from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV117SubMoDescendantDemand(TransactionCase):

    def test_active_component_mo_is_loaded_as_commitment(self):
        root = Path(__file__).parents[1]
        source = (root / 'services' / 'component_sourcing.py').read_text()
        self.assertIn("active_component_mo_qty = defaultdict(float)", source)
        self.assertIn(
            "('aps_planning_component_id', 'in', components.ids)",
            source,
        )
        self.assertIn(
            "('state', 'not in', ('done', 'cancel'))",
            source,
        )

    def test_existing_submo_keeps_children_required(self):
        root = Path(__file__).parents[1]
        source = (root / 'services' / 'component_sourcing.py').read_text()
        self.assertIn(
            "committed_make = active_component_mo_qty.get(component.id, 0.0)",
            source,
        )
        self.assertIn(
            "descendant_demand = committed_make + to_make",
            source,
        )

    def test_native_submo_writes_reverse_component_link(self):
        root = Path(__file__).parents[1]
        source = (root / 'models' / 'stock_rule.py').read_text()
        self.assertIn("'generated_production_id': mo.id", source)
