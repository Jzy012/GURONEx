# utils/admin_data.py

from django.core.exceptions import ObjectDoesNotExist
from adminhub.models import AdminProfile  # adjust import path

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
