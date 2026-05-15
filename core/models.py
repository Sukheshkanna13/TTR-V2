import uuid
from django.conf import settings
from django.db import models


class Attraction(models.Model):
    CATEGORY_CHOICES = [
        ('TEMPLE', 'Temple'),
        ('BEACH', 'Beach'),
        ('MUSEUM', 'Museum'),
        ('RESTAURANT', 'Restaurant'),
        ('SHOPPING', 'Shopping'),
        ('NATURE', 'Nature'),
        ('EVENT', 'Event'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    city = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    description = models.TextField(blank=True, default='')
    address = models.CharField(max_length=300, blank=True, default='')
    opening_hrs = models.CharField(max_length=200, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    is_visible = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attractions_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'attraction'
        verbose_name_plural = 'attractions'

    def __str__(self):
        return f"{self.name} ({self.city})"

    @property
    def primary_photo(self):
        return self.photos.filter(is_primary=True).first() or self.photos.first()


class AttractionPhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attraction = models.ForeignKey(
        Attraction,
        on_delete=models.CASCADE,
        related_name='photos',
    )
    image = models.ImageField(upload_to='attraction_photos/')
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', '-is_primary']

    def __str__(self):
        return f"Photo for {self.attraction.name}"
