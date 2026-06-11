from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from applicant.models import Applicant

def applicant_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        pk = request.session.get("applicant_pk")
        if not pk:
            messages.error(request, "Please log in using your Applicant ID and Email.")
            return redirect("applicants:login")
        try:
            applicant = Applicant.objects.only('is_archived').get(pk=pk)
        except Applicant.DoesNotExist:
            request.session.pop("applicant_pk", None)
            return redirect("applicants:login")
        if applicant.is_archived:
            return redirect("applicants:inactive")
        return view_func(request, *args, **kwargs)
    return _wrapped