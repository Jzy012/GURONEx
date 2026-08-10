# base/templatetags/appearance_tags.py

from django import template
from django.conf import settings
from django.core.cache import cache
from pathlib import Path

from base.models import LandingAppearance, LANDING_CACHE_KEY, LANDING_CACHE_TTL

register = template.Library()


def _landing_data():
    """
    Cached landing-page appearance data. Collapses the two get_solo() calls and
    the MEDIA_ROOT file stat into a single cached dict so a warm homepage render
    does zero DB round-trips. Invalidated on LandingAppearance.save() and when
    the background image is (re)uploaded.
    """
    data = cache.get(LANDING_CACHE_KEY)
    if data is None:
        appearance = LandingAppearance.get_solo()
        bg_exists = (Path(settings.MEDIA_ROOT) / "backgrounds" / "landing-bg.jpg").exists()
        data = {
            "use_background_image": appearance.use_background_image,
            "overlay_style": appearance.overlay_style,
            "bg_exists": bg_exists,
        }
        cache.set(LANDING_CACHE_KEY, data, LANDING_CACHE_TTL)
    return data


@register.filter
def get_item(dictionary, key):
    """Dict lookup by variable key: {{ my_dict|get_item:key }}"""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def format_phone(value):
    """Format a stored 11-digit PH number (09171234567) as (0917 123 4567) for display."""
    if not value:
        return value or ""
    digits = str(value).replace(" ", "").replace("-", "")
    if len(digits) == 11:
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
    return value


@register.simple_tag
def landing_background_url():
    """
    Returns the background image URL if enabled and present, otherwise an empty string.
    """
    data = _landing_data()
    if not data["use_background_image"]:
        return ""

    if not data["bg_exists"]:
        return ""

    # Use the explicit Django view instead of /media/...
    return "/background-image/"

@register.simple_tag
def landing_background_overlay_classes():
    """
    Returns classes for an overlay div depending on the configured style.
    - none:        no overlay classes
    - dark:        semi-transparent dark overlay
    - silhouette:  grayscale + darkened "silhouette" look (requires CSS helper)
    """
    style = _landing_data()["overlay_style"]

    if style == LandingAppearance.OVERLAY_DARK:
        # Simple dark overlay (keeps color, just darkens)
        return "bg-black/40"
    elif style == LandingAppearance.OVERLAY_SILHOUETTE:
        # Use a custom utility class defined in your CSS
        return "bg-silhouette-overlay"
    else:
        # 'none' or anything unexpected: no overlay
        return ""