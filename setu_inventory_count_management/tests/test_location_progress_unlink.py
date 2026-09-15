# -*- coding: utf-8 -*-
from pathlib import Path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestLocationProgressUnlink(TransactionCase):

    def test_obsolete_progress_removed_from_existing_before_mapped(self):
        module = Path(__file__).resolve().parents[1]
        code = (
            module / "models/inventory_count_location_flow.py"
        ).read_text(encoding="utf-8")

        self.assertIn("existing -= obsolete", code)
        self.assertIn("obsolete.unlink()", code)

        remove_pos = code.index("existing -= obsolete")
        unlink_pos = code.index("obsolete.unlink()", remove_pos)
        mapped_pos = code.index('existing.mapped("location_id")', unlink_pos)

        self.assertLess(remove_pos, unlink_pos)
        self.assertLess(unlink_pos, mapped_pos)
