# from odoo import http


# class JkkReport(http.Controller):
#     @http.route('/jkk_report/jkk_report', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/jkk_report/jkk_report/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('jkk_report.listing', {
#             'root': '/jkk_report/jkk_report',
#             'objects': http.request.env['jkk_report.jkk_report'].search([]),
#         })

#     @http.route('/jkk_report/jkk_report/objects/<model("jkk_report.jkk_report"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('jkk_report.object', {
#             'object': obj
#         })

