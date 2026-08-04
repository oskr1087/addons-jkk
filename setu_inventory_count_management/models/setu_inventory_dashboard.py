# -*- coding: utf-8 -*-
from datetime import datetime, date, timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError
import calendar
from collections import defaultdict
from datetime import datetime, date
import logging

_logger = logging.getLogger(__name__)


class SetuInventoryDashboard(models.AbstractModel):
    _name = 'setu.inventory.dashboard'
    _description = 'Inventory Count Dashboard'

    def _get_valid_counts(self, counts):
        """Filter counts to only include valid states"""
        return counts.filtered(lambda c: c.state in ['Approved', 'Inventory Adjusted'])

    def _get_date_range(self, start_date, end_date):
        """Reusable method to parse and normalize date range"""
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
        return start_dt.date(), end_dt.date()

    def _build_base_domains(self, start_date, end_date, warehouse_ids=None, session_ids=None):
        """Build common domains for sessions and counts"""
        session_domain = [
            ('session_start_date', '>=', start_date),
            ('session_submit_date', '<=', end_date),
            ('state', 'not in', ['Draft', 'In Progress', 'Cancel']),
        ]

        count_domain = [
            ('inventory_count_date', '>=', start_date),
            ('inventory_count_date', '<=', end_date),
            ('state', 'in', ['Approved', 'Inventory Adjusted']),
        ]

        if warehouse_ids:
            session_domain.append(('warehouse_id', 'in', warehouse_ids))
            count_domain.append(('warehouse_id', 'in', warehouse_ids))

        if session_ids:
            session_domain.append(('id', 'in', session_ids))

        return session_domain, count_domain

    def _get_filtered_sessions(self, domain, user_ids=None):
        """Get sessions with optional user filtering"""
        if user_ids:
            domain.append(('user_ids', 'in', user_ids))
        return self.env['setu.inventory.count.session'].search(domain)

    def _get_filtered_counts(self, count_domain, session_ids):
        """Get counts filtered by sessions"""
        if session_ids:
            count_domain.append(('session_ids', 'in', session_ids.ids))
        return self.env['setu.stock.inventory.count'].search(count_domain)

    def _format_duration(self, total_seconds):
        """Format seconds to HH:MM:SS"""
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @api.model
    def get_dashboard_data(self, start_date, end_date, warehouse_ids=None, user_ids=None, session_ids=None):
        """Get dashboard data for inventory count management"""
        start_dt, end_dt = self._get_date_range(start_date, end_date)
        session_domain, count_domain = self._build_base_domains(start_dt, end_dt, warehouse_ids, session_ids)

        # Get filtered sessions and counts
        sessions = self._get_filtered_sessions(session_domain, user_ids)
        counts = self._get_filtered_counts(count_domain, sessions)
        counts = self._get_valid_counts(counts)
        # Get pending sessions
        pending_sessions = self._get_filtered_sessions(
            session_domain + [('state', '=', 'Submitted')],
            user_ids
        )

        # Calculate KPIs
        return {
            'total_sessions_completed': self._get_total_sessions_completed(sessions),
            'avg_time_per_session': self._get_avg_time_per_session(sessions),
            'total_products_counted': self._get_total_products_counted(counts,user_ids),
            'global_accuracy': self._get_global_accuracy(counts,user_ids),
            'total_discrepancy_qty': self._get_total_discrepancy_qty(counts,user_ids),
            'total_inventory_loss': self._get_total_inventory_loss(counts,user_ids),
            'approvals_pending': self._get_approvals_pending(pending_sessions),
        }

    def _get_total_sessions_completed(self, sessions):
        """Count of all sessions in filter"""
        return len(sessions.filtered(lambda s: s.state in ['Done', 'Submitted']))

    def _get_avg_time_per_session(self, sessions):
        """Average time per session"""
        completed_sessions = sessions.filtered(lambda s: s.state in ['Done', 'Submitted'])
        if not completed_sessions:
            return self._format_duration(0)

        total_seconds = 0
        for session in completed_sessions:
            session_details = self.env['setu.inventory.session.details'].search([('session_id', '=', session.id)])
            total_seconds += sum(session_details.mapped('duration_seconds'))

        avg_seconds = total_seconds / len(completed_sessions)
        return self._format_duration(avg_seconds)

    def _get_total_products_counted(self, counts, user_ids=None):
        """Unique products counted by selected users"""
        count_lines = counts.mapped("line_ids")
        if user_ids:
            count_lines = count_lines.filtered(
                lambda cl: cl.user_ids and any(u.id in user_ids for u in cl.user_ids))
        product_ids = count_lines.mapped("product_id").ids
        return len(set(product_ids))

    def _get_global_accuracy(self, counts, user_ids=None):
        """Calculate global accuracy percentage for selected users"""
        if not counts:
            return 0.0
        count_lines = counts.mapped("line_ids")
        if user_ids:
            count_lines = count_lines.filtered(
                lambda cl: cl.user_ids and any(u.id in user_ids for u in cl.user_ids))
        all_products = count_lines.mapped("product_id")
        if not all_products:
            return 0.0
        products_with_discrepancy = count_lines.filtered(lambda l: l.is_discrepancy_found).mapped("product_id")
        accurate_products = set(all_products) - set(products_with_discrepancy)
        accuracy_ratio = (len(accurate_products) / len(all_products)) * 100
        return round(accuracy_ratio, 2)

    def _get_total_discrepancy_qty(self, counts, user_ids=None):
        """Total number of discrepancies found by selected users"""
        if not counts:
            return 0
        count_lines = counts.mapped("line_ids")
        if user_ids:
            count_lines = count_lines.filtered(
                lambda cl: cl.user_ids and any(u.id in user_ids for u in cl.user_ids))
        return len(count_lines.filtered(lambda l: l.is_discrepancy_found))

    def _get_total_inventory_loss(self, counts, user_ids=None):
        """Total inventory loss value for selected users"""
        if not counts:
            return 0.0
        count_lines = counts.mapped("line_ids")
        if user_ids:
            count_lines = count_lines.filtered(
                lambda cl: cl.user_ids and any(u.id in user_ids for u in cl.user_ids))
        loss_lines = count_lines.filtered(
            lambda l: l.is_discrepancy_found and l.difference_qty < 0.0)
        return abs(sum(loss_lines.mapped('discrepancy_value')))

    def _get_approvals_pending(self, sessions):
        """Number of sessions pending approval"""
        return len(sessions)

    @api.model
    def get_warehouse_list(self):
        """Get list of warehouses for filter"""
        warehouses = self.env['stock.warehouse'].search([])
        return [{'id': w.id, 'name': w.name} for w in warehouses]

    @api.model
    def get_user_list(self):
        """Get list of users for filter"""
        users = self.env['res.users'].search([('active', '=', True)])
        return [{'id': u.id, 'name': u.name} for u in users]

    @api.model
    def get_session_list(self, user_ids):
        """Get list of sessions for filter, filtered by selected users"""
        domain = []
        if user_ids:
            domain = [('user_ids', 'in', user_ids)]
        sessions = self.env['setu.inventory.count.session'].search(domain)
        return [{'id': s.id, 'name': s.name} for s in sessions]

    def _get_chart_data_domains(self, start_date, end_date, warehouse_ids=None, user_ids=None, session_ids=None):
        """Build common domains for chart data"""
        start_dt, end_dt = self._get_date_range(start_date, end_date)

        session_domain = [
            ('session_start_date', '>=', start_dt),
            ('session_submit_date', '<=', end_dt),
            ('session_id', '=', False),
            ('state', 'not in', ['Draft', 'In Progress', 'Cancel']),
        ]

        count_domain = [
            ('inventory_count_date', '>=', start_dt),
            ('inventory_count_date', '<=', end_dt),
        ]

        if warehouse_ids:
            session_domain.append(('warehouse_id', 'in', warehouse_ids))
            count_domain.append(('warehouse_id', 'in', warehouse_ids))

        if session_ids:
            session_domain.append(('id', 'in', session_ids))
            count_domain.append(('session_ids', 'in', session_ids))

        return session_domain, count_domain, start_dt, end_dt

    def _get_user_mistakes_data(self, session_lines):
        """Get user mistakes vs accuracy data"""
        user_to_stats = defaultdict(lambda: {'accurate': 0, 'mistake': 0})

        for line in session_lines:
            for user in line.user_ids:
                key = user.name
                if line.user_calculation_mistake:
                    user_to_stats[key]['mistake'] += 1
                else:
                    user_to_stats[key]['accurate'] += 1

        users_labels = list(user_to_stats.keys())
        return {
            'labels': users_labels,
            'accurate': [user_to_stats[n]['accurate'] for n in users_labels],
            'mistake': [user_to_stats[n]['mistake'] for n in users_labels],
        }

    def _get_discrepancy_by_location_data(self, count_lines):
        """Get discrepancy data grouped by location"""
        loc_to_count = defaultdict(int)
        for line in count_lines:
            if line.is_discrepancy_found:
                key = line.location_id.display_name or 'N/A'
                loc_to_count[key] += 1

        loc_labels = list(loc_to_count.keys())
        return {
            'labels': loc_labels,
            'values': [loc_to_count[key] for key in loc_labels],
        }

    def _get_discrepancy_trend_data(self, count_lines):
        """Get discrepancy trend over time"""
        date_to_value = defaultdict(float)
        for line in count_lines:
            count_date = line.inventory_count_id.inventory_count_date
            if count_date:
                date_to_value[count_date] += line.discrepancy_value or 0.0

        sorted_dates = sorted(date_to_value.keys())
        return {
            'labels': [d.strftime('%Y-%m-%d') for d in sorted_dates],
            'values': [round(date_to_value[d], 2) for d in sorted_dates],
        }

    def _get_top_products_loss_data(self, count_lines):
        """Get top 10 products by loss"""
        loss_lines = count_lines.filtered(lambda cl: cl.discrepancy_value < 0)
        prod_to_loss = defaultdict(float)

        for line in loss_lines:
            product_name = line.product_id.display_name
            prod_to_loss[product_name] += line.discrepancy_value

        top_items = sorted(prod_to_loss.items(), key=lambda x: x[1])[:10]
        return {
            'labels': [name for name, _ in top_items],
            'values': [round(value, 2) for _, value in top_items],
        }

    def _get_mistake_reasons_data(self, session_lines):
        """Get mistake reasons distribution"""
        discrepancy_lines = session_lines.filtered(lambda sl: sl.is_discrepancy_found)
        user_mistakes = sum(1 for l in discrepancy_lines if l.user_calculation_mistake)
        system_mistakes = len(discrepancy_lines) - user_mistakes

        total = user_mistakes + system_mistakes
        if total > 0:
            user_percent = round((user_mistakes / total) * 100, 2)
            system_percent = round((system_mistakes / total) * 100, 2)
        else:
            user_percent = system_percent = 0.0

        return {
            'labels': ['User Mistakes', 'System Mistakes'],
            'values': [user_percent, system_percent],
        }

    @api.model
    def get_chart_data(self, start_date, end_date, warehouse_ids=None, user_ids=None, session_ids=None):
        """Returns datasets for all charts based on the same filters as the KPIs."""
        session_domain, count_domain, start_dt, end_dt = self._get_chart_data_domains(
            start_date, end_date, warehouse_ids, user_ids, session_ids
        )

        # Get sessions and counts
        sessions = self._get_filtered_sessions(session_domain, user_ids)
        counts = self.env['setu.stock.inventory.count'].search(count_domain)

        # Get session lines and count lines
        session_lines = sessions.mapped('session_line_ids')
        counts = self._get_valid_counts(counts)
        count_lines = counts.mapped('line_ids')

        # Apply user filters to lines
        if user_ids:
            session_lines = session_lines.filtered(
                lambda sl: sl.user_ids and any(u.id in user_ids for u in sl.user_ids)
            )
            count_lines = count_lines.filtered(
                lambda cl: cl.user_ids and any(u.id in user_ids for u in cl.user_ids)
            )

        # Build chart data
        return {
            'users': self._get_user_mistakes_data(session_lines),
            'discrepancy_by_location': self._get_discrepancy_by_location_data(count_lines),
            'discrepancy_trend': self._get_discrepancy_trend_data(count_lines),
            'top_products_loss': self._get_top_products_loss_data(count_lines),
            'mistake_reasons': self._get_mistake_reasons_data(session_lines),
        }

    def _get_table_data_domains(self, start_date, end_date, warehouse_ids=None, session_ids=None):
        """Build common domains for table data"""
        start_dt, end_dt = self._get_date_range(start_date, end_date)

        session_domain = [
            ('session_start_date', '>=', start_dt),
            ('session_start_date', '<=', end_dt),
        ]

        count_domain = [
            ('inventory_count_date', '>=', start_dt),
            ('inventory_count_date', '<=', end_dt),
            ('state','in',['Approved', 'Inventory Adjusted'])
        ]

        if warehouse_ids:
            session_domain.append(('warehouse_id', 'in', warehouse_ids))
            count_domain.append(('warehouse_id', 'in', warehouse_ids))

        if session_ids:
            session_domain.append(('id', 'in', session_ids))
            count_domain.append(('session_ids', 'in', session_ids))

        return session_domain, count_domain

    def _get_open_sessions(self, domain, user_ids=None):
        """Get data for Open Sessions table"""
        try:
            local_domain = domain + [('state', 'in', ['In Progress', 'Submitted'])]
            if user_ids:
                local_domain.append(('user_ids', 'in', user_ids))
            sessions = self.env['setu.inventory.count.session'].search(
                local_domain, limit=6, order='session_start_date desc'
            )

            return [{
                'id': s.id,
                'name': s.name or 'N/A',
                'warehouse': s.warehouse_id.name if s.warehouse_id else 'N/A',
                'users': ', '.join(s.user_ids.mapped('name')) if s.user_ids else 'N/A',
                'start_time': s.session_start_date.strftime('%Y-%m-%d %H:%M') if s.session_start_date else 'N/A',
            } for s in sessions]
        except Exception as e:
            _logger.error("Error in _get_open_sessions: %s", str(e))
            return []

    def _get_recent_adjustments(self, count_domain, user_ids=None):
        """Get data for Recent Adjustments table"""
        try:
            counts = self.env['setu.stock.inventory.count'].search(count_domain, order='inventory_count_date desc')
            lines = counts.mapped('line_ids').filtered(lambda cl: cl.is_discrepancy_found)

            if user_ids:
                lines = lines.filtered(
                    lambda l: l.user_ids and any(u.id in user_ids for u in l.user_ids)
                )

            return [{
                'id': line.inventory_count_id.id or 0,
                'model': 'setu.stock.inventory.count',
                'name': line.inventory_count_id.name or 'N/A',
                'product': line.product_id.display_name or 'N/A',
                'theoretical': line.theoretical_qty or 0,
                'counted': line.counted_qty or 0,
                'adjustment': f"{line.difference_qty or 0} (₹{abs(line.discrepancy_value or 0):.2f})",
            } for line in lines[:5]]
        except Exception as e:
            _logger.error("Error in _get_recent_adjustments: %s", str(e))
            return []

    def _get_high_risk_products(self, count_domain, user_ids=None):
        """Get data for High-Risk Products table"""
        try:
            counts = self.env['setu.stock.inventory.count'].search(count_domain, order='inventory_count_date desc')
            lines = counts.mapped('line_ids').filtered(lambda cl: cl.is_discrepancy_found)

            if user_ids:
                lines = lines.filtered(
                    lambda l: l.user_ids and any(u.id in user_ids for u in l.user_ids)
                )

            product_stats = {}
            for line in lines:
                if not line.product_id:
                    continue

                product_name = line.product_id.display_name
                if product_name not in product_stats:
                    product_stats[product_name] = {
                        'count': 0,
                        'discrepancy_sum': 0,
                        'last_date': date.min,
                        'product_id': line.product_id.id
                    }

                stats = product_stats[product_name]
                stats['count'] += 1

                if line.theoretical_qty and line.theoretical_qty > 0:
                    stats['discrepancy_sum'] += abs((line.difference_qty or 0) / line.theoretical_qty) * 100

                count_date = line.inventory_count_id.inventory_count_date
                if count_date and count_date > stats['last_date']:
                    stats['last_date'] = count_date

            # Sort by count and take top 5
            sorted_products = sorted(
                product_stats.items(),
                key=lambda x: x[1]['count'],
                reverse=True
            )[:5]

            return [{
                'id': stats['product_id'],
                'model': 'product.product',
                'name': name,
                'times_counted': stats['count'],
                'avg_discrepancy': f"{(stats['discrepancy_sum'] / stats['count']):.2f}%" if stats[
                                                                                                'count'] > 0 else "0.00%",
                'last_discrepancy_date': stats['last_date'].strftime('%Y-%m-%d') if stats[
                                                                                        'last_date'] != date.min else 'N/A',
            } for name, stats in sorted_products]
        except Exception as e:
            _logger.error("Error in _get_high_risk_products: %s", str(e))
            return []

    @api.model
    def get_table_data(self, start_date, end_date, warehouse_ids=None, user_ids=None, session_ids=None):
        """Get data for the drill-down tables."""
        try:
            session_domain, count_domain = self._get_table_data_domains(
                start_date, end_date, warehouse_ids, session_ids
            )

            return {
                'open_sessions': self._get_open_sessions(session_domain, user_ids),
                'recent_adjustments': self._get_recent_adjustments(count_domain, user_ids),
                'high_risk_products': self._get_high_risk_products(count_domain, user_ids),
            }
        except Exception as e:
            _logger.error("Error in get_table_data: %s", str(e))
            return {
                'open_sessions': [],
                'recent_adjustments': [],
                'high_risk_products': [],
            }
