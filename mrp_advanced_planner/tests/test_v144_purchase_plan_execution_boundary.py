from pathlib import Path


def _source():
    return (Path(__file__).parents[1] / "models" / "planning_plan.py").read_text()


def _method_source(name):
    source = _source()
    marker = f"    def {name}("
    section = source.split(marker, 1)[1]
    next_def = section.find("\n    def ")
    return section if next_def < 0 else section[:next_def]


def test_calculate_does_not_sync_purchase_plan():
    assert "_sync_component_purchase_plan(" not in _method_source("action_calculate")


def test_smart_button_does_not_create_or_refresh_purchase_plan():
    section = _method_source("action_open_generated_purchase_plan")
    assert "_sync_component_purchase_plan(" not in section
    assert "_refresh_component_sourcing(" not in section
    assert "generated_purchase_plan_id" in section


def test_fabricar_is_the_purchase_plan_execution_boundary():
    section = _method_source("action_create_manufacturing")
    assert "self._sync_component_purchase_plan()" in section
