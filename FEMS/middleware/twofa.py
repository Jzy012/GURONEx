from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

class TwoFAMiddleware(MiddlewareMixin):
    def process_request(self, request):
        pre_2fa_user_id = request.session.get("pre_2fa_user_id")

        # Exempted routes (login, verify 2fa, logout)
        exempt_paths = {
            reverse('login'),
            reverse('verify_2fa_otp'),
            reverse('logout'),  # Optional
        }

        # If user is in the middle of 2FA, enforce it globally
        if pre_2fa_user_id and request.path not in exempt_paths:
            return redirect('verify_2fa_otp')

        return None
