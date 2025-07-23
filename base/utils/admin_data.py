# utils/admin_data.py

from django.core.exceptions import ObjectDoesNotExist
from adminhub.models import AdminProfile  # adjust import path


from faculty.models import FacultyProfile
from faculty.models import FacultyDocument  # If you need document status, etc.
from django.db.models import Count, Q, Prefetch



# Fetch admin data for the logged-in user

def get_admin_data(request):
    try:
        profile = request.user.admin_profile
    except ObjectDoesNotExist:
        return {}

    return {
        'profile': profile,
        'name': profile.name,
        'contact_number': profile.contact_number,
        'two_factor_enabled': request.user.two_factor_authentication,
    }



# Fetch all faculty data 


def get_all_faculty_data():
    faculty_qs = FacultyProfile.objects.select_related('account', 'status').order_by('name')

    data = []
    for faculty in faculty_qs:
        documents = faculty.documents.all()

        data.append({
            'id': faculty.id,
            'uuid': faculty.uuid,
            'name': faculty.name,
            'email': faculty.account.email,
            'department': faculty.department,
            'contact_number': faculty.contact_number,
            'status': faculty.status.name if faculty.status else 'Unassigned',
            'gdrive_folder_id': faculty.gdrive_folder_id,
            'document_count': documents.count(),
            'pending_documents': documents.filter(status='Pending').count(),
        })

    return {'faculty_list': data}
