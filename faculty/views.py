from django.shortcuts import render, redirect
from base.decorators import faculty_required, admin_required
from base.forms import TwoFactorToggleForm
from django.contrib import messages
# Create your views here.

@faculty_required
def home(request):
    
    return render(request, 'faculty/faculty_home.html')


@faculty_required
def faculty_settings_view(request):
    return render(request, 'faculty/faculty_settings.html')


@faculty_required
def faculty_2fa(request):
    user = request.user

    if request.method == 'POST':
        form = TwoFactorToggleForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "2FA setting updated.")
            return redirect("faculty:faculty_2fa")
    else:
        form = TwoFactorToggleForm(instance=user)

    return render(request, "faculty/faculty_2fa.html", {"form": form})
