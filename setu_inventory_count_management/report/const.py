from datetime import datetime

import pytz


def get_dynamic_query(location, location_ids, user, user_ids, warehouse, warehouse_ids):
    where_query = ''
    if location_ids:
        where_query += f"""and  1 = case when array_length({location_ids},1) >= 1 then
                        case when {location} = ANY({location_ids}) then 1 else 0 end
                        else 1 end
    """
    if user_ids:
        where_query += f"""and 1 = case when array_length({user_ids},1) >= 1 then
                            case when {user} = ANY({user_ids}) then 1 else 0 end
                            else 1 end
    """
    if warehouse_ids:
        where_query += f"""and 1 = case when array_length({warehouse_ids},1) >= 1 then
                            case when {warehouse} = ANY({warehouse_ids}) then 1 else 0 end
                            else 1 end
    """
    return where_query


def change_time_zone(local_timezone, datetime_obj):
    local_timezone = pytz.timezone(local_timezone)
    datetime_obj = datetime.strptime(f"{datetime_obj}", "%Y-%m-%d %H:%M:%S")
    local_dt = local_timezone.localize(datetime_obj, is_dst=None)
    utc_dt = local_dt.astimezone(pytz.utc)
    return utc_dt
