# base/media_views.py
from django.conf import settings
from django.http import FileResponse, Http404
from pathlib import Path

def serve_landing_background(request):
    """
    Serve the current landing background image from MEDIA_ROOT/backgrounds/landing-bg.jpg.
    """
    file_path = Path(settings.MEDIA_ROOT) / "backgrounds" / "landing-bg.jpg"
    if not file_path.exists():
        raise Http404("landing-bg.jpg not found")

    # You can change content_type if your file is PNG, etc.
    return FileResponse(open(file_path, "rb"), content_type="image/jpeg")