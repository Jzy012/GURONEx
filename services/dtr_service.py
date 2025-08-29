from datetime import datetime, timedelta, date
import pytz
from django.utils import timezone
from faculty.models import TeachingAssignment
from rfid.models import AttendanceLog

class DTRCalculator:
    LATE_MINUTES = 45
    MANILA_TZ = pytz.timezone('Asia/Manila')

    @staticmethod
    def get_assignments_for_day(faculty, day):
        day_of_week = day.strftime('%a').lower()[:3]
        return TeachingAssignment.objects.filter(
            faculty=faculty,
            day_of_week=day_of_week,
            semester__start_date__lte=day,
            semester__end_date__gte=day
        )

    @staticmethod
    def get_logs_for_day(faculty, day):
        return AttendanceLog.objects.filter(faculty=faculty, date=day).order_by('time_in')

    @staticmethod
    def calculate_status(assignment, log):
        if not log or not log.time_in:
            return 'absent'

        manila_tz = DTRCalculator.MANILA_TZ

        scheduled_in = manila_tz.localize(datetime.combine(log.date, assignment.start_time))
        scheduled_out = manila_tz.localize(datetime.combine(log.date, assignment.end_time))
        actual_in = timezone.localtime(log.time_in, manila_tz)
        actual_out = timezone.localtime(log.time_out, manila_tz) if log.time_out else None

        # EARLY IN detection: more than 30 minutes before scheduled_in
        early_threshold = timedelta(minutes=30)
        delta_in = actual_in - scheduled_in
        if delta_in < -early_threshold:
            return 'early in'

        # Check overtime first
        if actual_out:
            overtime_threshold = scheduled_out + timedelta(hours=1)
            if actual_out >= overtime_threshold:
                return 'overtime'

        # If not overtime, check lateness
        if delta_in > timedelta(minutes=DTRCalculator.LATE_MINUTES):
            return 'late'
        else:
            return 'on time'

    @classmethod
    def get_dtr_for_month(cls, faculty, year, month):
        from calendar import monthrange

        manila_tz = cls.MANILA_TZ
        days_in_month = monthrange(year, month)[1]
        dtr_result = []
        for day_num in range(1, days_in_month + 1):
            current_date = date(year, month, day_num)
            assignments = cls.get_assignments_for_day(faculty, current_date)
            logs = list(cls.get_logs_for_day(faculty, current_date))
            status_list = []
            for assignment in assignments:
                # Use the earliest log for the day (if any) for this assignment
                matched_log = logs[0] if logs else None
                status = cls.calculate_status(assignment, matched_log)
                status_list.append({
                    'assignment': assignment,
                    'attendance_log': matched_log,
                    'status': status,
                })
            if not assignments:
                status_list.append({'assignment': None, 'attendance_log': None, 'status': 'no assignment'})
            dtr_result.append({
                'date': current_date,
                'statuses': status_list,
            })
        return dtr_result