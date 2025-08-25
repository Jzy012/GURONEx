from datetime import datetime, timedelta, date
from faculty.models import TeachingAssignment
from rfid.models import AttendanceLog

class DTRCalculator:
    LATE_MINUTES = 45

    @staticmethod
    def get_assignments_for_day(faculty, day):
        """
        Returns teaching assignments for a faculty on a specific day,
        only if the assignment's semester covers that date and matches the weekday.
        """
        day_of_week = day.strftime('%a').lower()[:3]  # 'mon', 'tue', etc.
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
        scheduled_in = datetime.combine(log.date, assignment.start_time)
        scheduled_out = datetime.combine(log.date, assignment.end_time)
        actual_in = log.time_in
        actual_out = log.time_out

        # Check overtime first
        if actual_out:
            overtime_threshold = scheduled_out + timedelta(hours=1)
            if actual_out >= overtime_threshold:
                return 'overtime'

        # If not overtime, check lateness
        delta_in = actual_in - scheduled_in
        if delta_in > timedelta(minutes=DTRCalculator.LATE_MINUTES):
            return 'late'
        else:
            return 'on time'

    @classmethod
    def get_dtr_for_month(cls, faculty, year, month):
        """
        For each day of the given month, returns a list of assignments
        (with attendance and status) for that day's valid teaching assignments.
        Only assignments whose semester covers the date will be included.
        """
        from calendar import monthrange

        days_in_month = monthrange(year, month)[1]
        dtr_result = []
        for day_num in range(1, days_in_month + 1):
            current_date = date(year, month, day_num)
            assignments = cls.get_assignments_for_day(faculty, current_date)
            logs = list(cls.get_logs_for_day(faculty, current_date))
            status_list = []
            for assignment in assignments:
                # Assign each log to the nearest assignment
                matched_log = None
                for log in logs:
                    # Check if log falls within a reasonable window
                    if assignment.start_time <= log.time_in.time() <= assignment.end_time:
                        matched_log = log
                        break
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