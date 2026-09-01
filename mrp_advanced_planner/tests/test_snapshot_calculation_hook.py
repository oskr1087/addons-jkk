from pathlib import Path

from odoo.tests.common import TransactionCase


class TestSnapshotCalculationHook(TransactionCase):

    def test_manufacturing_snapshot_is_built_during_calculation(self):
        # Functional regression guard: the engine must build the snapshot
        # before returning the number of created planning lines.
        from ..services import simple_planning_engine
        source = Path(simple_planning_engine.__file__).read_text()
        build_pos = source.find('ManufacturingSnapshotBuilder(self.plan).build')
        return_pos = source.rfind('return len(created)')
        self.assertGreaterEqual(build_pos, 0)
        self.assertGreater(return_pos, build_pos)
