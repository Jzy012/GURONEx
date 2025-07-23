
# login & logout imports

from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from .forms import LoginForm
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from base.decorators import faculty_required, admin_required



# forgot password imports

from django.contrib.auth import get_user_model
from .forms import ForgotPasswordForm
from .models import UserOTP
from base.utils.emailotp_utils import send_otp_email 

from .forms import OTPVerificationForm, TwoFactorOTPVerificationForm
from django.utils import timezone

from django.contrib.auth.hashers import make_password
from django.contrib.auth import get_user_model, login
from .forms import PasswordResetForm



# Google Drive OAuth imports

from django.http import HttpResponse
from services.google_oauth_service import GoogleOAuthService  # adjust path as needed
from base.decorators import admin_required  # adjust import path if needed

from base.models import GoogleStorageAccount
from services.google_oauth_service import GoogleOAuthService

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Create your views here.

def index(request):
    return render(request, 'index.html')



def login_view(request):
    if request.user.is_authenticated:
        # Auto-redirect if already logged in
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
                if user.two_factor_authentication:
                    # ✅ Trigger 2FA via email
                    otp_obj = UserOTP.create_for_user(user, purpose='login_2fa', expiry_minutes=5)
                    send_otp_email(user.email, otp_obj.otp, purpose='login_2fa')
                    request.session['pre_2fa_user_id'] = user.id
                    messages.info(request, 'A login OTP has been sent to your email.')
                    return redirect('verify_2fa_otp')
                else:
                    # Normal login
                    auth_login(request, user)
                    if user.role == 'admin':
                        return redirect('adminhub:home')
                    elif user.role == 'faculty':
                        return redirect('faculty:home')
            else:
                messages.error(request, 'Invalid credentials.')
    else:
        form = LoginForm()

    return render(request, 'authentication/login.html', {'form': form}) 


def logout_view(request):
    user = request.user
    logout(request)

    

    # Default fallback redirect
    return redirect('login')




# Forgot Password Views

MAX_OTP_REQUESTS_PER_DAY = 10

def forgot_password_view(request):
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            User = get_user_model()
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                # Do not reveal whether the email exists
                messages.success(request, "If your email is registered, you will receive an OTP.")
                return redirect("forgot_password")

            # Check OTP requests per day
            otp_requests = UserOTP.otp_requests_today(user, purpose='password_reset')
            if otp_requests >= MAX_OTP_REQUESTS_PER_DAY:
                messages.error(request, "Maximum OTP requests reached for today. Please try again tomorrow.")
                return redirect("forgot_password")

            # Create OTP and send email
            otp_obj = UserOTP.create_for_user(user, purpose='password_reset', expiry_minutes=10)
            send_otp_email(email, otp_obj.otp, purpose='password_reset')
            messages.success(request, "If your email is registered, you will receive an OTP.")
            return redirect("verify_otp")
    else:
        form = ForgotPasswordForm()
    return render(request, "authentication/forgot_password.html", {"form": form})




def verify_otp_view(request):
    if request.method == "POST":
        form = OTPVerificationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            otp = form.cleaned_data["otp"]
            User = get_user_model()
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                messages.error(request, "Invalid OTP or email.")
                return redirect("verify_otp")

            # Get most recent active OTP
            otp_obj = UserOTP.objects.filter(
                user=user,
                purpose='password_reset',
                is_used=False,
                expires_at__gt=timezone.now()
            ).order_by("-created_at").first()


            if otp_obj and otp_obj.otp == otp:
                if otp_obj.has_expired():
                    messages.error(request, "OTP has expired. Please request a new one.")
                    return redirect("forgot_password")
                otp_obj.mark_as_used()
                # Save user id in session for next step
                request.session["reset_user_id"] = user.id
                messages.success(request, "OTP verified. Please reset your password.")
                return redirect("reset_password")
            else:
                messages.error(request, "Invalid OTP or email.")
    else:
        form = OTPVerificationForm()
    return render(request, "authentication/verify_otp.html", {"form": form})


from django.contrib.auth.forms import SetPasswordForm


def reset_password_view(request):
    user_id = request.session.get("reset_user_id")
    if not user_id:
        messages.error(request, "Session expired or invalid. Please try the password reset process again.")
        return redirect("forgot_password")

    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect("forgot_password")

    if request.method == "POST":
        form = SetPasswordForm(user, request.POST)  # ✅ Pass user as first argument
        if form.is_valid():
            form.save()  # ✅ Handles password hashing + validation
            del request.session["reset_user_id"]
            messages.success(request, "Password reset successful.")
            return redirect("login")
    else:
        form = SetPasswordForm(user)

    return render(request, "authentication/reset_password.html", {"form": form})




# Two-Factor Authentication Views

def verify_two_factor_otp_view(request):
    User = get_user_model()
    user_id = request.session.get("pre_2fa_user_id")

    if not user_id:
        messages.error(request, "Session expired or invalid.")
        return redirect("login")

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect("login")

    if request.method == "POST":
        form = TwoFactorOTPVerificationForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data["otp"]

            otp_obj = UserOTP.objects.filter(
                user=user,
                purpose='login_2fa',
                is_used=False,
                expires_at__gt=timezone.now()
            ).order_by("-created_at").first()

            if otp_obj and otp_obj.otp == otp:
                if otp_obj.has_expired():
                    messages.error(request, "OTP has expired. Please log in again.")
                    return redirect("login")

                otp_obj.mark_as_used()
                del request.session["pre_2fa_user_id"]
                auth_login(request, user)

                # Redirect based on role
                if user.role == 'admin':
                    return redirect("adminhub:home")
                elif user.role == 'faculty':
                    return redirect("faculty:home")
            else:
                messages.error(request, "Invalid or expired OTP.")
    else:
        form = TwoFactorOTPVerificationForm()

    return render(request, "authentication/verify_two_factor_otp.html", {"form": form})




# Google Drive OAuth Views


@admin_required
def authorize_google(request):
    oauth_service = GoogleOAuthService(request.user)
    auth_url = oauth_service.get_auth_url()
    return redirect(auth_url)

@admin_required
def oauth2callback(request):
    code = request.GET.get("code")
    if not code:
        return HttpResponse("No code provided", status=400)

    oauth_service = GoogleOAuthService(request.user)
    creds = oauth_service.exchange_code_for_token(code)

    # Decode the ID token to get email
    token_info = id_token.verify_oauth2_token(
        creds.id_token, google_requests.Request(), audience=creds.client_id
    )

    email = token_info.get("email")

    # Save to GoogleStorageAccount
    GoogleStorageAccount.objects.update_or_create(
        email=email,
        defaults={
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_expiry": creds.expiry,
            "is_active": True,
        }
    )

    return HttpResponse("✅ Storage account connected successfully!")