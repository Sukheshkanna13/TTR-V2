from core.models import SiteBanner


def site_banners(request):
    """
    Context processor to provide active site banners to templates.
    Caches the primary active banner per target_page.
    """
    try:
        banners = SiteBanner.objects.filter(is_active=True).order_by('sort_order', '-created_at')
        banner_map = {}
        for b in banners:
            if b.target_page not in banner_map:
                banner_map[b.target_page] = b
        return {
            'site_banners': banner_map,
            'home_hero_banner': banner_map.get('home'),
        }
    except Exception:
        return {'site_banners': {}, 'home_hero_banner': None}
