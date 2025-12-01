from datetime import timedelta, datetime

def calculate_total_working_hours(rows):
    total = timedelta()
    for row in rows:
        def parse_time(val):
            try:
                return datetime.strptime(val, "%I:%M %p").time() if val else None
            except Exception:
                return None

        am_in  = parse_time(row.get('am_in', ''))
        am_out = parse_time(row.get('am_out', ''))
        pm_in  = parse_time(row.get('pm_in', ''))
        pm_out = parse_time(row.get('pm_out', ''))

        # Calculate AM/PM intervals if complete
        for start, end in [(am_in, am_out), (pm_in, pm_out)]:
            if start and end:
                dt_start = timedelta(hours=start.hour, minutes=start.minute)
                dt_end   = timedelta(hours=end.hour, minutes=end.minute)
                interval = dt_end - dt_start
                if interval > timedelta():
                    total += interval

    hours = total.total_seconds() // 3600
    minutes = (total.total_seconds() % 3600) // 60
    return f"{int(hours)}h {int(minutes):02d}m"