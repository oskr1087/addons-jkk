from . import test_planner

from . import test_confirmed_mo_supply

from . import test_recursive_purchase_demand

from . import test_aps_component_snapshot

from . import test_snapshot_calculation_hook

from . import test_component_availability_ui

from . import test_availability_action_structure

from . import test_sale_forecast_fields

from . import test_v60_hardening

from . import test_component_sourcing_flow

from . import test_submo_snapshot_routing

from . import test_purchase_duplicate_prevention

from . import test_odoo19_raw_move_contract

from . import test_no_component_mo_generation

from . import test_v66_cutoff_dynamic_subcontract

from . import test_v67_bidirectional_traceability

from . import test_v68_sale_unified_availability

from . import test_v69_sale_availability_wizard

from . import test_v70_sale_availability_ui

from . import test_v71_component_editor_and_purchase_validation

from . import test_v73_subcontract_snapshot

from . import test_v74_component_modification_validation

from . import test_v75_empty_calculation_reusable

from . import test_v76_component_lock_after_mo

from . import test_v76_1_engineering_lock_compute

from . import test_v76_2_internal_transfer_odoo19

from . import test_v77_optional_transfers

from . import test_v78_lot_reservation

from . import test_v79_pending_lot_supply


from . import test_v81_route_based_sale_manufacturing_hold

from . import test_v82_stock_lot_qr_report

from . import test_v82_1_report_name

from . import test_v82_2_qr_embedded_widget

from . import test_v82_3_qr_payload_count

from . import test_v83_security_profiles

from . import test_v83_2_qr_pda_format

from . import test_v84_1_delivery_menu

from . import test_v84_2_delivery_view_fields

from . import test_v84_3_searchable_plan_count

from . import test_v84_4_calendar_status_dates

from . import test_v84_5_calendar_plan_day

from . import test_v84_6_click_calendar_day

from . import test_v84_7_pending_day_real_traceability

from . import test_v84_8_day_and_previous_pending

from . import test_v84_9_explicit_sale_shortage

from . import test_v84_10_detail_create_fields

from . import test_v84_11_lot_reassign_reload

from . import test_v84_12_lot_physical_visibility

from . import test_v84_13_compact_component_tree

from . import test_v84_14_lot_states_capacity

from . import test_v84_15_direct_lot_assignment

from . import test_v85_planning_observations

from . import test_v85_4_resolution_required

from . import test_v85_5_supply_labels

from . import test_v85_6_tags_and_flow

from . import test_v85_7_customer_mo_regression

from . import test_v85_8_lot_move_compatibility

from . import test_v90_process_hardening

from . import test_v91_safe_rollback

from . import test_v92_cancel_guard_all_documents

from . import test_v93_component_types_and_chain

from . import test_v94_lot_reassignment_between_mos

from . import test_v95_date_end_date_only

from . import test_v96_date_datetime_comparison

from . import test_v97_native_submanufacturing

from . import test_v98_cancel_component_stock_move_fk

from . import test_v99_no_duplicate_snapshot_on_manufacture

from . import test_v100_native_submo_with_components

from . import test_v101_plan_shows_only_root_mos

from . import test_v102_availability_native_submo

from . import test_v103_own_aps_reserved_availability

from . import test_v104_nonstockable_component_availability

from . import test_v105_all_date_datetime_comparisons

from . import test_v106_recalculate_without_duplicate_components

from . import test_v107_freeze_sourcing_after_manufacture

from . import test_v108_date_end_local_timezone

from . import test_v109_no_replan_same_sale_demand

from . import test_v110_date_only_planning

from . import test_v111_recalculate_after_done_transfer

from . import test_v112_nonstockable_never_requires_lot

from . import test_v113_nonstockable_root_mo_lot_guard

from . import test_v114_odoo19_exclude_requiring_lot_semantics

from . import test_v115_nonstockable_action_done

from . import test_v116_action_done_return_contract

from . import test_v117_submo_descendant_demand

from . import test_v118_existing_submo_repair

from . import test_v119_sale_supply_commitment

from . import test_v120_committed_elsewhere_traceability

from . import test_v121_receipt_reserves_existing_submo

from . import test_v122_lot_capacity_after_receipt

from . import test_v123_purchase_supply_commitment

from . import test_v124_demand_commitment_and_sequences
from . import test_v125_native_submo_procurement

from . import test_v126_recalculation_refresh

from . import test_v127_existing_root_submo

from . import test_v128_submo_only_on_recalculate

from . import test_v129_native_stock_rule_procurement

from . import test_v130_child_lot_reservation_owner

from . import test_v131_child_owner_before_confirm

from . import test_v132_same_plan_lot_usage

from . import test_v133_manufacturing_lifecycle

from . import test_v137_manufacturable_leaf_bom

from . import test_v138_recalculate_fabricate_recursive_identity
from . import test_v140_calculate_no_execution
from . import test_v141_fabricate_generates_purchase_plan
