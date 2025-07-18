from django.shortcuts import render, redirect 
from base.decorators import admin_required, faculty_required
from base.forms import TwoFactorToggleForm
from django.contrib import messages
from base.utils.admin_data import get_admin_data

# Create your views here.

@admin_required
def home(request):
    data = get_admin_data(request)
    return render(request, 'admin/admin_home.html', data)

    

    return render(request, 'admin/admin_home.html')


@admin_required
def documents(request):
    

    return render (request, 'admin/admin_documents_storage.html')


@admin_required
def admin_settings(request):
    return render(request, 'admin/admin_settings.html') 


@admin_required
def admin_2fa(request):
    user = request.user

    if request.method == 'POST':
        form = TwoFactorToggleForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "2FA setting updated.")
            return redirect("adminhub:admin_2fa")
    else:
        form = TwoFactorToggleForm(instance=user)

    return render(request, "admin/admin_2fa.html", {"form": form})
