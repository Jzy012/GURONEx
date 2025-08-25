from datetime import timedelta, date, datetime


class AttendanceStatusService:
    LATE_THRESHOLD = timedelta(minutes=45)

    @staticmethod
    def get_status(assignment, attendance_log):
        """
        assignment: TeachingAssignment instance
        attendance_log: AttendanceLog instance (can be None)

        Returns: 'ontime', 'late', 'overtime', 'absent'
        """
        if attendance_log is None or attendance_log.time_in is None:
            return 'absent'
        scheduled_in = assignment.start_time
        scheduled_out = assignment.end_time
        actual_in = attendance_log.time_in.time()
        # Check if late
        delta = datetime.combine(date.min, actual_in) - datetime.combine(date.min, scheduled_in)
        if delta > AttendanceStatusService.LATE_THRESHOLD:
            return 'late'
        elif delta < timedelta(minutes=0):
            return 'ontime'  # Early
        else:
            return 'ontime'
        # Add overtime logic if needed

    @staticmethod
    def get_status_for_multiple_assignments(assignments, attendance_logs):
        """
        assignments: list of TeachingAssignment for the day
        attendance_logs: list of AttendanceLog for the faculty that day

        Returns: dict {assignment_id: status}
        """
        # Map logs to times
        results = {}
        for assignment in assignments:
            # Find closest log for the assignment
            relevant_log = None
            min_delta = None
            for log in attendance_logs:
                # Only consider logs within a reasonable window
                log_time = log.time_in.time()
                delta = abs(datetime.combine(date.min, log_time) - datetime.combine(date.min, assignment.start_time))
                if min_delta is None or delta < min_delta:
                    relevant_log = log
                    min_delta = delta
            results[assignment.id] = AttendanceStatusService.get_status(assignment, relevant_log)
        return results