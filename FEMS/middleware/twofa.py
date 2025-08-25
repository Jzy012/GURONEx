from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

class TwoFAMiddleware(MiddlewareMixin):
    def process_request(self, request):
        pre_2fa_user_id = request.session.get("pre_2fa_user_id")

        # Exempted routes (login, verify 2fa, logout, etc.)
        exempt_paths = {
            reverse('login'),
            reverse('verify_2fa_otp'),
            reverse('forgot_password'),
            reverse('verify_otp'),
            reverse('resend_otp'),
            reverse('reset_password'),
            reverse('logout'),  
            reverse('admin:index'),  # admin homepage
        }

        # ✅ Also exempt *all* admin URLs by prefix
        if request.path.startswith("/system-config/"):
            return None

        # Enforce 2FA globally
        if pre_2fa_user_id and request.path not in exempt_paths:
            return redirect('verify_2fa_otp')

        return None
