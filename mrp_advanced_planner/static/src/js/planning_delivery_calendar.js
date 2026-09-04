/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CalendarController } from "@web/views/calendar/calendar_controller";
import { calendarView } from "@web/views/calendar/calendar_view";


export class ApsDeliveryCalendarController extends CalendarController {
    /**
     * In this dedicated APS delivery calendar an empty-day click is not a
     * request to create a sale.order.line. It opens the APS planning wizard with the clicked calendar date already selected.
     * The wizard plans every still-unplanned sale line due on or before that date.
     *
     * Keeping create="0" on the calendar remains intentional: sale lines
     * cannot be created from this agenda. FullCalendar still sends dateClick
     * to createRecord; this controller gives that click APS semantics.
     */
    async createRecord(record) {
        const planningDate = record?.start?.toISODate?.();
        if (!planningDate) {
            return;
        }

        return this.action.doAction({
            type: "ir.actions.act_window",
            name: "Planificar entregas del día",
            res_model: "mrp.planning.calendar.day.wizard",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_planning_date: planningDate,
            },
        });
    }
}


export const apsDeliveryCalendarView = {
    ...calendarView,
    Controller: ApsDeliveryCalendarController,
};

registry.category("views").add(
    "aps_delivery_calendar",
    apsDeliveryCalendarView
);
