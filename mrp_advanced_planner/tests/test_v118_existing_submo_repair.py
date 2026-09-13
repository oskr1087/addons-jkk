from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV118ExistingSubMoRepair(TransactionCase):

    def test_existing_submos_repair_reverse_link(self):
        root = Path(__file__).parents[1]
        source = (root / 'services' / 'component_sourcing.py').read_text()
        self.assertIn(
            "('aps_planning_component_id', 'in', components.ids)",
            source,
        )
        self.assertIn("'generated_production_id': mo.id", source)

    def test_descendant_demand_does_not_double_count_existing_submo(self):
        root = Path(__file__).parents[1]
        source = (root / 'services' / 'component_sourcing.py').read_text()
        self.assertIn(
            'descendant_demand = max(committed_make, to_make)',
            source,
        )
        self.assertNotIn(
            'descendant_demand = committed_make + to_make',
            source,
        )
