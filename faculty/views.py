from django.shortcuts import render, redirect
from base.decorators import faculty_required, admin_required
# Create your views here.

@faculty_required
def home(request):
    
    return render(request, 'faculty/faculty_home.html')


@faculty_required
def faculty_settings_view(request):
    return render(request, 'faculty/faculty_settings.html')