from django.shortcuts import render, redirect 
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login 


# Create your views here.

@login_required(login_url='login')
def home(request):
    if request.user.role != 'admin':
        return redirect( 'faculty:home')

    return render(request, 'admin_home.html')