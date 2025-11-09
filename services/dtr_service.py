from datetime import datetime, timedelta, date
import pytz
from django.utils import timezone
from faculty.models import TeachingAssignment
from rfid.models import AttendanceLog

class DTRCalculator:
    LATE_MINUTES = 45
    EARLY_MINUTES = 30
    MANILA_TZ = pytz.timezone('Asia/Manila')

    @staticmethod
    def get_assignments_for_day(faculty, day):
        day_of_week = day.strftime('%a').lower()[:3]
        return TeachingAssignment.objects.filter(
            faculty=faculty,
            day_of_week=day_of_week,
            semester__start_date__lte=day,
            semester__end_date__gte=day
        ).order_by('start_time')

    @staticmethod
    def get_log_for_day(faculty, day):
        # Only one log per day per faculty
        try:
            return AttendanceLog.objects.get(faculty=faculty, date=day)
        except AttendanceLog.DoesNotExist:
            return None

    @staticmethod
    def get_closest_assignment(assignments, dt):
        """
        Find the assignment which start_time is closest to dt but not after dt.
        If all assignments are after dt, return the earliest assignment.
        """
        dt_time = dt.time()
        assignments = list(assignments)
        eligible = [a for a in assignments if a.start_time <= dt_time]
        if eligible:
            # Closest eligible assignment (not after time_in)
            return min(eligible, key=lambda a: abs(datetime.combine(date.min, a.start_time) - datetime.combine(date.min, dt_time)))
        else:
            # If all assignments are after time_in, use the earliest
            return min(assignments, key=lambda a: a.start_time) if assignments else None

    @staticmethod
    def calculate_assignment_status(assignment, log, is_early_in_assignment):
        # If no log or time_in, faculty is absent for this assignment
        if not log or not log.time_in:
            return 'absent'
        manila_tz = DTRCalculator.MANILA_TZ

        scheduled_in = manila_tz.localize(datetime.combine(log.date, assignment.start_time))
        scheduled_out = manila_tz.localize(datetime.combine(log.date, assignment.end_time))
        actual_in = timezone.localtime(log.time_in, manila_tz)
        actual_out = timezone.localtime(log.time_out, manila_tz) if log.time_out else None

        # EARLY IN for the closest assignment only
        if is_early_in_assignment:
            early_threshold = timedelta(minutes=DTRCalculator.EARLY_MINUTES)
            delta_in = actual_in - scheduled_in
            if delta_in < -early_threshold:
                return 'early in'
            elif delta_in > timedelta(minutes=DTRCalculator.LATE_MINUTES):
                return 'late'
            elif delta_in >= timedelta(0):
                return 'on time'
            else:
                return 'on time' # Arrived between early threshold and on time

        # For other assignments, credit if time_out is within/after scheduled_out
        if actual_out:
            # Overtime check
            overtime_threshold = scheduled_out + timedelta(hours=1)
            if actual_out >= overtime_threshold:
                return 'overtime'
            # Credited if time_out is within/after scheduled end time
            if actual_out >= scheduled_out:
                delta_in = actual_in - scheduled_in
                if delta_in > timedelta(minutes=DTRCalculator.LATE_MINUTES):
                    return 'late'
                elif delta_in < timedelta(0):
                    return 'on time'
                else:
                    return 'on time'
            else:
                return 'absent'
        else:
            # No time_out: still credit if actual_in is before or at scheduled_out
            if actual_in <= scheduled_out:
                delta_in = actual_in - scheduled_in
                if delta_in > timedelta(minutes=DTRCalculator.LATE_MINUTES):
                    return 'late, no time out'
                elif is_early_in_assignment:
                    early_threshold = timedelta(minutes=DTRCalculator.EARLY_MINUTES)
                    if delta_in < -early_threshold:
                        return 'early in, no time out'
                return 'on time, no time out'
            else:
                return 'absent'

    @classmethod
    def get_dtr_for_month(cls, faculty, year, month):
        from calendar import monthrange

        manila_tz = cls.MANILA_TZ
        days_in_month = monthrange(year, month)[1]
        dtr_result = []
        for day_num in range(1, days_in_month + 1):
            current_date = date(year, month, day_num)
            assignments = list(cls.get_assignments_for_day(faculty, current_date))
            log = cls.get_log_for_day(faculty, current_date)
            status_list = []

            if not assignments:
                status_list.append({'assignment': None, 'attendance_log': log, 'status': 'no assignment'})
            else:
                # If there is a log, find the closest assignment for time_in
                is_early_in_assignment_id = None
                if log and log.time_in:
                    actual_in = timezone.localtime(log.time_in, manila_tz)
                    closest_assignment = cls.get_closest_assignment(assignments, actual_in)
                    if closest_assignment:
                        is_early_in_assignment_id = closest_assignment.id

                for assignment in assignments:
                    is_early_in_assignment = assignment.id == is_early_in_assignment_id
                    status = cls.calculate_assignment_status(assignment, log, is_early_in_assignment)
                    status_list.append({
                        'assignment': assignment,
                        'attendance_log': log,
                        'status': status,
                    })

            dtr_result.append({
                'date': current_date,
                'statuses': status_list,
            })

        return dtr_result