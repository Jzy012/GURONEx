from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

# Create your views here.

@login_required
def home(request):
    if request.user.role != 'faculty':
        return redirect( 'adminhub:home')

    return render(request, 'faculty_home.html')