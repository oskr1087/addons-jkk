# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

MODULE = "setu_inventory_count_management"
MODEL = "setu.stock.inventory.count"

BASE_XMLID = "setu_stock_inventory_count_form_view"
SNAPSHOT_XMLID = "setu_stock_inventory_count_snapshot_form_extension"
LEGACY_XMLID = "setu_stock_inventory_count_form_modern"

BASE_NAME = "setu_stock_inventory_count.form"
SNAPSHOT_NAME = "setu.stock.inventory.count.snapshot.form.extension"


def _get_imd(cr, xmlid):
    cr.execute(
        """
        SELECT id, res_id
          FROM ir_model_data
         WHERE module = %s
           AND name = %s
           AND model = 'ir.ui.view'
         ORDER BY id
        """,
        (MODULE, xmlid),
    )
    return cr.fetchall()


def _find_exact_view(cr, name, inherited):
    inherit_clause = "IS NOT NULL" if inherited else "IS NULL"
    cr.execute(
        f"""
        SELECT id
          FROM ir_ui_view
         WHERE model = %s
           AND name = %s
           AND inherit_id {inherit_clause}
         ORDER BY active DESC, id DESC
         LIMIT 1
        """,
        (MODEL, name),
    )
    row = cr.fetchone()
    return row[0] if row else None


def _other_external_ids(cr, view_id):
    cr.execute(
        """
        SELECT module, name
          FROM ir_model_data
         WHERE model = 'ir.ui.view'
           AND res_id = %s
         ORDER BY id
        """,
        (view_id,),
    )
    return cr.fetchall()


def _ensure_xmlid(cr, name, view_id):
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = %s
           AND name = %s
           AND model = 'ir.ui.view'
        """,
        (MODULE, name),
    )
    cr.execute(
        """
        INSERT INTO ir_model_data
            (module, name, model, res_id, noupdate)
        VALUES
            (%s, %s, 'ir.ui.view', %s, FALSE)
        """,
        (MODULE, name, view_id),
    )


def migrate(cr, version):
    _logger.warning(
        "SETU inventory count: starting canonical view XML-ID repair "
        "before loading module XML. Previous version: %s", version
    )

    xmlids = (BASE_XMLID, SNAPSHOT_XMLID, LEGACY_XMLID)
    old_targets = set()

    # Capture and remove every problematic alias first.
    for xmlid in xmlids:
        rows = _get_imd(cr, xmlid)
        for imd_id, res_id in rows:
            old_targets.add(res_id)
            cr.execute("DELETE FROM ir_model_data WHERE id = %s", (imd_id,))
            _logger.warning(
                "Removed stale/candidate alias %s.%s -> ir.ui.view(%s).",
                MODULE, xmlid, res_id,
            )

    # Identify trustworthy canonical view records independently of XML IDs.
    base_view_id = _find_exact_view(cr, BASE_NAME, inherited=False)
    snapshot_view_id = _find_exact_view(cr, SNAPSHOT_NAME, inherited=True)

    _logger.warning(
        "Canonical candidates found: base=%s snapshot=%s",
        base_view_id, snapshot_view_id,
    )

    # A crossed database can have the same physical view behind multiple aliases.
    # Canonical records must be distinct.
    if base_view_id and snapshot_view_id and base_view_id == snapshot_view_id:
        _logger.error(
            "Base and snapshot candidates resolve to the same ir.ui.view(%s). "
            "They will be recreated from XML.",
            base_view_id,
        )
        old_targets.add(base_view_id)
        base_view_id = None
        snapshot_view_id = None

    # If a candidate exists, reattach the correct canonical alias.
    # Otherwise XML loading will create it from the module source.
    if base_view_id:
        cr.execute(
            "UPDATE ir_ui_view SET active = TRUE WHERE id = %s",
            (base_view_id,),
        )
        _ensure_xmlid(cr, BASE_XMLID, base_view_id)
        _logger.warning(
            "Reattached canonical base XML ID to ir.ui.view(%s).",
            base_view_id,
        )

    if snapshot_view_id:
        cr.execute(
            "UPDATE ir_ui_view SET active = TRUE WHERE id = %s",
            (snapshot_view_id,),
        )
        _ensure_xmlid(cr, SNAPSHOT_XMLID, snapshot_view_id)
        _logger.warning(
            "Reattached canonical snapshot XML ID to ir.ui.view(%s).",
            snapshot_view_id,
        )

    canonical_ids = {view_id for view_id in (base_view_id, snapshot_view_id) if view_id}

    # Disable stale targets only when they are not one of the canonical records.
    # This prevents old inherited views from participating in composition.
    for view_id in old_targets - canonical_ids:
        refs = _other_external_ids(cr, view_id)
        # We do not delete business data or unrelated views. We simply disable
        # a stale count-form view when it belongs to the count model.
        cr.execute(
            """
            UPDATE ir_ui_view
               SET active = FALSE
             WHERE id = %s
               AND model = %s
            """,
            (view_id, MODEL),
        )
        _logger.warning(
            "Disabled stale count-form ir.ui.view(%s). Remaining XML IDs: %s",
            view_id, refs,
        )

    # The obsolete modern alias must never survive.
    cr.execute(
        """
        DELETE FROM ir_model_data
         WHERE module = %s
           AND name = %s
           AND model = 'ir.ui.view'
        """,
        (MODULE, LEGACY_XMLID),
    )

    _logger.warning(
        "SETU inventory count: canonical XML-ID repair completed."
    )
