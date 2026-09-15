# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestObservationReviewUX(TransactionCase):

    def test_observation_does_not_claim_automatic_recount(self):
        module = Path(__file__).resolve().parents[1]

        pda_py = (module / "models/pda_counting.py").read_text(encoding="utf-8")
        pda_xml = (module / "static/src/xml/pda_fast_count.xml").read_text(
            encoding="utf-8"
        )
        dashboard_xml = (
            module / "static/src/xml/count_backend_dashboard.xml"
        ).read_text(encoding="utf-8")

        forbidden = (
            "Observación registrada. Este producto irá a reconteo.",
            "Se enviará a reconteo al cerrar el conteo.",
            "Las líneas observadas serán candidatas a reconteo al cerrar el conteo.",
        )

        for text in forbidden:
            self.assertNotIn(text, pda_py)
            self.assertNotIn(text, pda_xml)
            self.assertNotIn(text, dashboard_xml)

        self.assertIn(
            "Observación registrada. Este producto quedará para revisión del controlador.",
            pda_py,
        )
        self.assertIn(
            "Quedará pendiente de revisión por el controlador.",
            pda_xml,
        )
        self.assertIn(
            "El controlador decidirá si se resuelven, se descartan, "
            "se envían a reconteo o se aprueban para ajuste.",
            dashboard_xml,
        )
