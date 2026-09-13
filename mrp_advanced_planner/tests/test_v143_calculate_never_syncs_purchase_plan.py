from pathlib import Path


def _method_source(name):
    source = (Path(__file__).parents[1] / "models" / "planning_plan.py").read_text()
    start = source.index(f"    def {name}(")
    tail = source[start + 1:]
    next_pos = tail.find("\n    def ")
    return source[start:] if next_pos < 0 else source[start:start + 1 + next_pos]


def test_calculate_never_syncs_component_purchase_plan():
    section = _method_source("action_calculate")
    assert "_sync_component_purchase_plan(" not in section


def test_purchase_plan_sync_only_at_explicit_execution_boundaries():
    open_section = _method_source("action_open_generated_purchase_plan")
    manufacture_section = _method_source("action_create_manufacturing")
    assert "_sync_component_purchase_plan()" in open_section
    assert "_sync_component_purchase_plan()" in manufacture_section
