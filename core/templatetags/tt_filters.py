from django import template
from django.utils.safestring import mark_safe

register = template.Library()

AMENITY_ICONS = {
    'wifi': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="WiFi"><path d="M5 12.55a11 11 0 0 1 14.08 0M1.42 9a16 16 0 0 1 21.16 0M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01"/></svg>',
    'ac': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="Air Conditioning"><rect x="2" y="6" width="20" height="8" rx="2"/><path d="M12 14v4M8 14v4M16 14v4"/></svg>',
    'pool': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="Swimming Pool"><path d="M2 12c1 0 2-1 3-1s2 1 3 1 2-1 3-1 2 1 3 1 2-1 3-1 2 1 3 1"/><path d="M2 18c1 0 2-1 3-1s2 1 3 1 2-1 3-1 2 1 3 1 2-1 3-1 2 1 3 1"/><circle cx="12" cy="6" r="2"/><path d="M12 8v4"/></svg>',
    'parking': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="Parking"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 17V7h4a3 3 0 0 1 0 6H9"/></svg>',
    'breakfast': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="Breakfast"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/></svg>',
    'hot_water': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="Hot Water"><path d="M12 22a8 8 0 0 0 8-8c0-4-8-12-8-12S4 10 4 14a8 8 0 0 0 8 8z"/></svg>',
    'tv': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="TV"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>',
    'balcony': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="Balcony"><path d="M3 9h18M3 9v10h18V9M7 9V5a2 2 0 0 1 4 0M13 9V5a2 2 0 0 1 4 0M7 14h10"/></svg>',
    'sea_view': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="Sea View"><path d="M2 16c1 0 2-1 3-1s2 1 3 1 2-1 3-1 2 1 3 1 2-1 3-1 2 1 3 1"/><path d="M2 20c1 0 2-1 3-1s2 1 3 1 2-1 3-1 2 1 3 1 2-1 3-1 2 1 3 1"/><circle cx="12" cy="8" r="3"/><path d="M12 2v3M4.2 10.8l2.1 2.1M19.8 10.8l-2.1 2.1"/></svg>',
    'garden_view': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="Garden View"><path d="M12 22V12M12 12C12 7 7 3 2 3c0 5 4 9 10 9zM12 12c0-5 5-9 10-9-0 5-4 9-10 9z"/></svg>',
}

DEFAULT_ICON = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-label="Amenity"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'


@register.filter
def amenity_icon(key):
    """Return a 20x20 inline SVG for the given amenity key (wifi, ac, pool, etc.)."""
    normalized = str(key).strip().lower().replace(' ', '_').replace('-', '_')
    return mark_safe(AMENITY_ICONS.get(normalized, DEFAULT_ICON))
