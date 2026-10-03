from django import template

register = template.Library()


@register.simple_tag
def page_url(request, page_number):
    """Querystring for `page_number` that keeps every other active filter."""
    params = request.GET.copy()
    params["page"] = page_number
    return "?" + params.urlencode()
