from django.shortcuts import render, redirect
from base.decorators import faculty_required, admin_required
# Create your views here.

@faculty_required
def home(request):
    
    return render(request, 'faculty_home.html')