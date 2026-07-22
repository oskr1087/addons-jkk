# Copyright © 2026 TugIT. All rights reserved.

from odoo import http
from odoo.http import request
import requests
import base64
import tempfile

class ZplLabelController(http.Controller):

    @http.route("/zpl-label-report", type="jsonrpc", auth="user", csrf=False)
    def render_zpl(self, **kw):
        action = kw.get("action")
        try:
            report_obj = request.env['ir.actions.report'].sudo()
            report_name = action.get('report_name')
            active_ids = action['context'].get('active_ids')
            if not report_name or not active_ids:
                return {'success':False, 'message': "No reports or active records provided."}
            report_id = report_obj.search([('report_name', '=', report_name)], limit=1)
            if report_id.report_type == 'qweb-text':
                zpl_command = report_obj._render_qweb_text(report_name, active_ids, data=action.get('data'))[0]
                return {'success':True, 'zpl_command': zpl_command}
            else:
                return {'success':False, 'message': "The report is not for ZPL."}
        except Exception as e:
            return {'success':False, 'message': f'Error in ZPL Label Report: {str(e)}'}
