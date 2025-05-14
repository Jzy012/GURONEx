from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from .forms import LoginForm
from django.contrib import messages
from django.contrib.auth import logout

# Create your views here.

def index(request):
    return render(request, 'index.html')



def login_view(request):
    if request.user.is_authenticated:
        # Redirect based on role
        if request.user.role == 'admin':
            return redirect('adminhub:home')
        elif request.user.role == 'faculty':
            return redirect('faculty:home')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, email=email, password=password)
            if user is not None:
                auth_login(request, user)
                # Redirect based on role
                if user.role == 'admin':
                    return redirect('adminhub:home')
                elif user.role == 'faculty':
                    return redirect('faculty:home')
            else:
                messages.error(request, 'Invalid credentials.')
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    user = request.user
    logout(request)

    

    # Default fallback redirect
    return redirect('login')