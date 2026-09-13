from pathlib import Path
from odoo.tests.common import TransactionCase


class TestV124DemandCommitmentAndSequences(TransactionCase):

    def test_sequences_are_split_by_plan_type(self):
        root = Path(__file__).parents[1]
        xml = (root / 'data' / 'planner_data.xml').read_text()
        model = (root / 'models' / 'planning_plan.py').read_text()

        self.assertIn('mrp.planning.plan.manufacturing', xml)
        self.assertIn('APS-FAB/', xml)
        self.assertIn('mrp.planning.plan.purchase', xml)
        self.assertIn('APS-COM/', xml)
        self.assertIn("'mrp.planning.plan.purchase'", model)
        self.assertIn("'mrp.planning.plan.manufacturing'", model)

    def test_exact_sale_line_is_commitment_not_same_product(self):
        root = Path(__file__).parents[1]
        source = (root / 'services' / 'simple_planning_engine.py').read_text()
        method = source.split(
            'def _sale_lines_already_committed_to_aps', 1
        )[1].split('def _sale_demand', 1)[0]

        self.assertIn("('plan_id.state', 'in', ('calculated', 'approved'))", method)
        self.assertIn("('sale_line_ids', 'in', sale_lines.ids)", method)
        self.assertIn("('sale_line_id', 'in', sale_lines.ids)", method)
        self.assertNotIn("'finalized'", method)

    def test_other_aps_soft_supply_is_not_used(self):
        root = Path(__file__).parents[1]
        simple = (root / 'services' / 'simple_planning_engine.py').read_text()
        component = (root / 'services' / 'component_sourcing.py').read_text()

        self.assertIn('other_plan_supply = defaultdict(float)', simple)
        self.assertIn('other_supply = defaultdict(float)', component)

    def test_other_aps_mo_is_not_generic_supply(self):
        root = Path(__file__).parents[1]
        simple = (root / 'services' / 'simple_planning_engine.py').read_text()
        component = (root / 'services' / 'component_sourcing.py').read_text()

        self.assertIn('mo.advanced_plan_id != self.plan', simple)
        self.assertIn('mo.advanced_plan_id != self.plan', component)
