from pathlib import Path

from odoo.tests.common import TransactionCase


class TestV71ComponentEditorAndPurchaseValidation(TransactionCase):

    def test_component_purchase_traceability_not_direct_demand(self):
        from ..models import planning_plan
        source = Path(planning_plan.__file__).read_text()
        self.assertIn("if line.source_type == 'mrp':", source)
        self.assertIn(
            "self.source_manufacturing_plan_id._validate_sale_lines_still_pending()",
            source,
        )

    def test_component_editor_has_operational_layout(self):
        root = Path(__file__).parents[1]
        source = (
            root / 'views' / 'planning_component_views.xml'
        ).read_text()
        self.assertIn('COMPONENTE A UTILIZAR', source)
        self.assertIn('DISPONIBILIDAD Y RESOLUCIÓN', source)
        self.assertIn('Trazabilidad de ingeniería', source)
        self.assertIn('planning_line_id" invisible="1"', source)

    def test_pending_availability_state_exists(self):
        field = self.env[
            'mrp.planning.production.component'
        ]._fields['availability_status']
        selection = field.selection
        if callable(selection):
            selection = selection(self.env)
        self.assertIn('pending', dict(selection))
