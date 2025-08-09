# middleware.py

from django.utils.deprecation import MiddlewareMixin

class AuthSensitiveCacheControlMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # Only modify if it's an HTML page (skip static, API, etc.)
        if 'text/html' in response.get('Content-Type', ''):
            if request.user.is_authenticated:
                # Allow caching but only in the browser (not shared caches)
                response['Cache-Control'] = 'private, no-store, must-revalidate'
            else:
                # Prevent caching if not authenticated (after logout, etc.)
                response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response['Pragma'] = 'no-cache'
                response['Expires'] = '0'
        return response
