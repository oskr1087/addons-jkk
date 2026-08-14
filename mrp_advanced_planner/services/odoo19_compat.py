from odoo import fields


def find_bom(env, product, company_id=False, picking_type_id=False):
    """Resolve _bom_find across supported Odoo 19 deployments."""
    model = env['mrp.bom']
    kwargs = {'company_id': company_id}
    if picking_type_id:
        kwargs['picking_type_id'] = picking_type_id
    try:
        result = model._bom_find(product, **kwargs)
    except TypeError:
        result = model._bom_find(product, company_id=company_id)
    if hasattr(result, 'get'):
        return result.get(product) or result.get(product.product_tmpl_id)
    return result


def subtract_work_days(calendar, value, days):
    if not value or not days:
        return value
    try:
        return calendar.plan_hours(-days * 24.0, value)
    except (AttributeError, TypeError):
        return fields.Datetime.subtract(value, days=days)
