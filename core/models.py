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

    objects = models.Manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    city = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    description = models.TextField(blank=True, default='')
    address = models.CharField(max_length=300, blank=True, default='')
    opening_hrs = models.CharField(max_length=200, blank=True, default='')
    whatsapp_link = models.URLField(
        max_length=2000,
        blank=True,
        default='',
        help_text="WhatsApp chat or group link for redirections."
    )
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

    # Type annotation for Pyrefly / static analysis (reverse ForeignKey relation)
    photos: models.Manager

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


class Cause(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=100)  # e.g. "KARNATAKA", "TAMIL NADU", "PAN-INDIA"
    description = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to='causes/', blank=True, null=True)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    raised_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    whatsapp_link = models.URLField(
        max_length=2000,
        blank=True,
        default='',
        help_text="Redirect link for this cause."
    )
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', '-created_at']
        verbose_name = 'cause'
        verbose_name_plural = 'causes'

    def __str__(self):
        return f"{self.title} ({self.location})"

    @property
    def progress_percentage(self):
        if self.target_amount <= 0:
            return 0
        percentage = (self.raised_amount / self.target_amount) * 100
        return min(int(percentage), 100)


class Activity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=100)  # e.g. "Outdoor", "Wellness", "Crafts"
    description = models.TextField(blank=True, default='')
    price = models.CharField(max_length=100, default='Request to book')
    image = models.ImageField(upload_to='activities/', blank=True, null=True)
    whatsapp_link = models.URLField(
        max_length=2000,
        blank=True,
        default='',
        help_text="Redirect link for this activity. If empty, uses default WhatsApp message."
    )
    whatsapp_message = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="WhatsApp prefilled message if custom link is not provided."
    )
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', '-created_at']
        verbose_name = 'activity'
        verbose_name_plural = 'activities'

    def __str__(self):
        return f"{self.title} ({self.category})"
