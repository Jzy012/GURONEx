from django.shortcuts import redirect
from functools import wraps

def role_required(role, redirect_to='login'):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')  # Clean redirect, no ?next=

            if request.user.role == role:
                return view_func(request, *args, **kwargs)
            
            # Redirect to another dashboard if the role is wrong
            return redirect(redirect_to)
        
        return _wrapped_view
    return decorator

# Shortcuts for specific roles
admin_required = role_required('admin', redirect_to='faculty:home')
faculty_required = role_required('faculty', redirect_to='adminhub:home')
