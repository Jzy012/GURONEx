from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages

def applicant_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get("applicant_pk"):
            messages.error(request, "Please log in using your Applicant ID and Email.")
            return redirect("applicants:login")
        return view_func(request, *args, **kwargs)
    return _wrapped