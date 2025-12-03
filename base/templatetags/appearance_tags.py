from django import template
from django.conf import settings
from pathlib import Path

from base.models import LandingAppearance

register = template.Library()


# base/templatetags/appearance_tags.py

from django import template
from django.conf import settings
from pathlib import Path

from base.models import LandingAppearance

register = template.Library()


@register.simple_tag
def landing_background_url():
    """
    Returns the background image URL if enabled and present, otherwise an empty string.
    """
    appearance = LandingAppearance.get_solo()
    if not appearance.use_background_image:
        return ""

    file_path = Path(settings.MEDIA_ROOT) / "backgrounds" / "landing-bg.jpg"
    if not file_path.exists():
        return ""

    return settings.MEDIA_URL + "backgrounds/landing-bg.jpg"

@register.simple_tag
def landing_background_overlay_classes():
    """
    Returns classes for an overlay div depending on the configured style.
    - none:        no overlay classes
    - dark:        semi-transparent dark overlay
    - silhouette:  grayscale + darkened "silhouette" look (requires CSS helper)
    """
    appearance = LandingAppearance.get_solo()
    style = appearance.overlay_style

    if style == LandingAppearance.OVERLAY_DARK:
        # Simple dark overlay (keeps color, just darkens)
        return "bg-black/40"
    elif style == LandingAppearance.OVERLAY_SILHOUETTE:
        # Use a custom utility class defined in your CSS
        return "bg-silhouette-overlay"
    else:
        # 'none' or anything unexpected: no overlay
        return ""