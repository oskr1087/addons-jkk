# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Remove obsolete inherited views from pre-6.5.5 versions.

    Older versions may have stored ir.ui.view records that reference
    auto_load_location_products/action_load_location_inventory. Those records
    must disappear before Odoo validates the new field-less model.
    """
    cr.execute("""
        SELECT v.id, d.id
          FROM ir_ui_view v
          JOIN ir_model_data d
            ON d.model = 'ir.ui.view'
           AND d.res_id = v.id
         WHERE d.module = 'setu_inventory_count_management'
           AND (
                v.arch_db::text ILIKE '%%auto_load_location_products%%'
             OR v.arch_db::text ILIKE '%%action_load_location_inventory%%'
           )
    """)
    rows = cr.fetchall()
    if not rows:
        return

    view_ids = [row[0] for row in rows]
    data_ids = [row[1] for row in rows]

    cr.execute("DELETE FROM ir_model_data WHERE id = ANY(%s)", (data_ids,))
    cr.execute("DELETE FROM ir_ui_view WHERE id = ANY(%s)", (view_ids,))
