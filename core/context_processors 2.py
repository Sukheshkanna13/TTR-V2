from django.core.cache import cache
from core.models import SiteBanner

CACHE_KEY_SITE_BANNERS = "ttr_site_banners_map"
CACHE_TTL = 3600  # 1 hour


def _load_banners():
    banners = SiteBanner.objects.filter(is_active=True).order_by('sort_order', '-created_at')
    banner_map = {}
    for b in banners:
        if b.target_page not in banner_map:
            banner_map[b.target_page] = b
    return banner_map


def site_banners(request):
    """
    Context processor to provide active site banners to templates.
    Caches the primary active banner per target_page for 1 hour with instant invalidation.
    """
    try:
        banner_map = cache.get_or_set(CACHE_KEY_SITE_BANNERS, _load_banners, timeout=CACHE_TTL)
        return {
            'site_banners': banner_map or {},
            'home_hero_banner': (banner_map or {}).get('home'),
        }
    except Exception:
        return {'site_banners': {}, 'home_hero_banner': None}
