from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.urls import reverse

from .forms import (
    CustomSetPasswordForm,
    LoginForm,
    ForgotPasswordForm,
    OTPVerificationForm,
    TwoFactorOTPVerificationForm,
    PasswordResetForm,
)
from .models import UserOTP
from base.decorators import faculty_required, admin_required
from base.utils.emailotp_utils import send_otp_email
from base.models import GoogleStorageAccount

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from services.google_oauth_service import GoogleOAuthService

# Constants
MAX_OTP_REQUESTS_PER_DAY = 20

# --------- Main Views --------- #

def index(request):
    return render(request, 'index.html')


@never_cache
def login_view(request):
    if request.user.is_authenticated:
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
                    otp_obj = UserOTP.create_for_user(user, purpose='login_2fa', expiry_minutes=5)
                    send_otp_email(user.email, otp_obj.otp, purpose='login_2fa')
                    request.session['pre_2fa_user_id'] = user.id
                    messages.info(request, 'A login OTP has been sent to your email.')
                    return redirect('verify_2fa_otp')
                else:
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
    logout(request)
    return redirect('login')


# --------- Forgot Password Views --------- #

def forgot_password_view(request):
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            User = get_user_model()
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                messages.success(request, "If your email is registered, you will receive an OTP.")
                return redirect("forgot_password")

            otp_requests = UserOTP.otp_requests_today(user, purpose='password_reset')
            if otp_requests >= MAX_OTP_REQUESTS_PER_DAY:
                messages.error(request, "Maximum OTP requests reached for today. Please try again tomorrow.")
                return redirect("forgot_password")

            otp_obj = UserOTP.create_for_user(user, purpose='password_reset', expiry_minutes=10)
            send_otp_email(email, otp_obj.otp, purpose='password_reset')
            request.session["otp_email"] = email

            messages.success(request, "If your email is registered, you will receive an OTP.")
            return redirect("verify_otp")
    else:
        form = ForgotPasswordForm()
    return render(request, "authentication/forgot_password.html", {"form": form})


@never_cache
def verify_otp_view(request):
    email = request.session.get("otp_email")
    if not email:
        messages.error(request, "Session expired. Please start again.")
        return redirect("forgot_password")

    if request.method == "POST":
        form = OTPVerificationForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data["otp"]
            User = get_user_model()
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                messages.error(request, "Invalid OTP.")
                return redirect("verify_otp")

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
                request.session["reset_user_id"] = user.id
                messages.success(request, "OTP verified. Please reset your password.")
                return redirect("reset_password")
            else:
                messages.error(request, "Invalid OTP.")
    else:
        form = OTPVerificationForm()

    return render(request, "authentication/verify_otp.html", {"form": form})


def resend_otp_view(request):
    email = request.session.get("otp_email")
    if not email:
        return JsonResponse({"success": False, "message": "Session expired. Try again."}, status=400)

    User = get_user_model()
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({"success": False, "message": "Account not found."}, status=404)

    otp_requests = UserOTP.otp_requests_today(user, purpose='password_reset')
    if otp_requests >= MAX_OTP_REQUESTS_PER_DAY:
        return JsonResponse({
            "success": False,
            "message": "You’ve reached the maximum number of OTP requests today. Please try again tomorrow."
        }, status=429)

    UserOTP.objects.filter(user=user, purpose="password_reset", is_used=False).update(is_used=True)

    otp_obj = UserOTP.create_for_user(user, purpose='password_reset', expiry_minutes=10)
    send_otp_email(email, otp_obj.otp, purpose='password_reset')

    return JsonResponse({"success": True, "message": "A new OTP has been sent."})


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
        form = CustomSetPasswordForm(user, request.POST or None)
        if form.is_valid():
            form.save()
            del request.session["reset_user_id"]
            messages.success(request, "Password reset successful.")
            return redirect("login")
    else:
        form = CustomSetPasswordForm(user)

    return render(request, "authentication/reset_password.html", {"form": form})


# --------- Two-Factor Authentication Views --------- #

@never_cache
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

                if user.role == 'admin':
                    return redirect("adminhub:home")
                elif user.role == 'faculty':
                    return redirect("faculty:home")
            else:
                messages.error(request, "Invalid or expired OTP.")
    else:
        form = TwoFactorOTPVerificationForm()

    return render(request, "authentication/verify_two_factor_otp.html", {"form": form})




from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth import get_user_model
# Ensure UserOTP and send_otp_email are imported

MAX_2FA_OTP_REQUESTS_PER_DAY = 20  # Set your preferred limit

def resend_two_factor_otp_view(request):
    user_id = request.session.get("pre_2fa_user_id")
    if not user_id:
        return JsonResponse({"success": False, "message": "Session expired. Try logging in again."}, status=400)

    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({"success": False, "message": "Account not found."}, status=404)

    # Check rate limit
    otp_requests = UserOTP.otp_requests_today(user, purpose='login_2fa')
    if otp_requests >= MAX_2FA_OTP_REQUESTS_PER_DAY:
        return JsonResponse({
            "success": False,
            "message": "You’ve reached the maximum number of code requests today. Please try again tomorrow."
        }, status=429)

    # Mark old OTPs as used
    UserOTP.objects.filter(user=user, purpose="login_2fa", is_used=False).update(is_used=True)

    # Generate new OTP and send (via email, SMS, etc.)
    otp_obj = UserOTP.create_for_user(user, purpose='login_2fa', expiry_minutes=10)
    send_otp_email(user.email, otp_obj.otp, purpose='login_2fa')

    return JsonResponse({"success": True, "message": "A new code has been sent."})


# --------- Google Drive OAuth Views --------- #

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

    token_info = id_token.verify_oauth2_token(
        creds.id_token, google_requests.Request(), audience=creds.client_id
    )
    email = token_info.get("email")

    # Deactivate other storage accounts
    GoogleStorageAccount.objects.exclude(email=email).update(is_active=False)

    account, _ = GoogleStorageAccount.objects.get_or_create(email=email)
    account.access_token = creds.token           # uses property setter (encrypted)
    account.refresh_token = creds.refresh_token  # uses property setter (encrypted)
    account.token_expiry = creds.expiry
    account.is_active = True
    account.save()

    return HttpResponse("✅ Storage account connected successfully!")


def google_drive_status(request):
    account = GoogleStorageAccount.objects.filter(is_active=True).first()
    if not account:
        status = "❌ Disconnected. Re-authentication required."
        reauth_url = reverse("authorize_google")
    elif account.token_expiry and account.token_expiry > timezone.now():
        status = f"✅ Connected. Expires at {account.token_expiry.strftime('%Y-%m-%d %H:%M:%S')}"
        reauth_url = None
    else:
        status = "⚠️ Token expired – re-authentication required."
        reauth_url = reverse("authorize_google")
    return render(request, "admin/admin_home.html", {
        "status": status,
        "reauth_url": reauth_url,
    })


def storage_status_view(request):
    account = GoogleStorageAccount.objects.filter(is_active=True).first()
    status = {
        "label": "Disconnected",
        "color": "bg-red-100 text-red-800",
        "message": "No active Google Drive account.",
    }

    if account:
        if account.token_expiry and account.token_expiry > timezone.now():
            status = {
                "label": "Connected",
                "color": "bg-green-100 text-green-800",
                "message": f"Active account: {account.email}",
            }
        else:
            status = {
                "label": "Expired",
                "color": "bg-yellow-100 text-yellow-800",
                "message": "Token expired — reauthentication required.",
            }

    return render(request, "admin/admin_storage_status.html", {"status": status})