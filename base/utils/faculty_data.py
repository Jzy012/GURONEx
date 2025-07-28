from django.core.exceptions import ObjectDoesNotExist
from faculty.models import FacultyProfile  #, FacultyDocument, AttendanceLog, DTR, RFIDTag  # adjust imports if needed
from adminhub.models import Announcement, AnnouncementViewLog
from django.utils import timezone
from django.db.models import Q


def get_faculty_data(request):
    try:
        profile = request.user.faculty_profile
    except ObjectDoesNotExist:
        return {}

    user = request.user
    today = timezone.now().date()


    # Fetch latest unseen important announcement for this role
    unseen_important = Announcement.objects.filter(
        is_important=True,
        visible_to_roles__contains=[user.role],
        start_date__lte=today
    ).filter(
        Q(end_date__gte=today) | Q(end_date__isnull=True)
    ).exclude(
        announcementviewlog__user=user
    ).order_by('-created_at').first()




    # documents = FacultyDocument.objects.filter(faculty=profile)
    # attendance_logs = AttendanceLog.objects.filter(faculty=profile).order_by('-date')[:10]  # latest 10 logs
    # dtr_records = DTR.objects.filter(faculty=profile).order_by('-year', '-month')
    # rfid_tag = RFIDTag.objects.filter(faculty=profile).first()

    return {
        'profile': profile,
        'name': profile.name,
        'department': profile.department,
        'birth_date': profile.birth_date,
        'contact_number': profile.contact_number,
        'employment_status': profile.status.name if profile.status else 'Unassigned',
        # 'documents': documents,
        # 'pending_documents': documents.filter(status='Pending'),
        # 'has_pending_docs': documents.filter(status='Pending').exists(),
        # 'attendance_logs': attendance_logs,
        # 'dtr_records': dtr_records,
        # 'rfid_uid': rfid_tag.uid if rfid_tag else None,
        # 'is_rfid_registered': bool(rfid_tag),
        'two_factor_enabled': request.user.two_factor_authentication,

        'important_announcement': unseen_important,

    }

# This function retrieves the faculty profile data, including documents, attendance logs, DTR records, and RFID tag information.