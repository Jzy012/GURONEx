from django.shortcuts import render
from django.conf import settings


def _ctx(extra=None):
    ctx = {'support_email': getattr(settings, 'SUPPORT_EMAIL', '')}
    if extra:
        ctx.update(extra)
    return ctx


def handler_400(request, exception=None):
    return render(request, '400.html', _ctx(), status=400)


def handler_403(request, exception=None):
    return render(request, '403.html', _ctx(), status=403)


def handler_404(request, exception=None):
    return render(request, '404.html', _ctx(), status=404)


def handler_500(request):
    return render(request, '500.html', _ctx(), status=500)
