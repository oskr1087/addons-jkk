# -*- coding: utf-8 -*-

def migrate(cr, version):
    legacy_terms = [
        'auto_load_location_products',
        'action_load_location_inventory',
        'action_open_pending_result_lines',
        'action_open_unexpected_result_lines',
        'pending_result_count',
        'unexpected_result_count',
        'pda_expected_lines',
        'pda_pending_lines',
        'pda_unexpected_lines',
    ]
    for term in legacy_terms:
        cr.execute("""
            SELECT v.id, d.id
              FROM ir_ui_view v
              JOIN ir_model_data d
                ON d.model = 'ir.ui.view'
               AND d.res_id = v.id
             WHERE d.module = 'setu_inventory_count_management'
               AND v.arch_db::text ILIKE %s
        """, ('%' + term + '%',))
        rows = cr.fetchall()
        if not rows:
            continue
        view_ids = [row[0] for row in rows]
        data_ids = [row[1] for row in rows]
        cr.execute("DELETE FROM ir_model_data WHERE id = ANY(%s)", (data_ids,))
        cr.execute("DELETE FROM ir_ui_view WHERE id = ANY(%s)", (view_ids,))
