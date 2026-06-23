from django.contrib import admin
from .models import Attraction, AttractionPhoto, Cause


class AttractionPhotoInline(admin.TabularInline):
    model = AttractionPhoto
    extra = 1


@admin.register(Attraction)
class AttractionAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'category', 'is_visible', 'sort_order']
    list_filter = ['city', 'category', 'is_visible']
    search_fields = ['name', 'city', 'description']
    inlines = [AttractionPhotoInline]


@admin.register(Cause)
class CauseAdmin(admin.ModelAdmin):
    list_display = ['title', 'location', 'target_amount', 'raised_amount', 'is_active', 'sort_order']
    list_filter = ['location', 'is_active']
    search_fields = ['title', 'location', 'description']

