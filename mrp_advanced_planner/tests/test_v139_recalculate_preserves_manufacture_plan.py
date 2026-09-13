from pathlib import Path


def test_v139_same_aps_mos_are_not_generic_supply():
    source = (Path(__file__).parents[1] / "services" / "component_sourcing.py").read_text()
    assert "if mo.advanced_plan_id == self.plan" in source
    assert "pending_manufacture_qty" in source
    assert "pending_make = max(to_make - committed_make, 0.0)" in source


def test_v139_procurement_uses_pending_quantity():
    source = (Path(__file__).parents[1] / "models" / "mrp_extensions.py").read_text()
    assert "component.pending_manufacture_qty > 1e-9" in source
    assert "procurement_qty = component.pending_manufacture_qty" in source
