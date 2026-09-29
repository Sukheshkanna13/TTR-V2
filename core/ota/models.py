"""
Channex OTA mapping + outbound outbox models.

These models live physically in ``core/ota/`` for modularity but are registered
under the ``core`` Django app (see ``app_label`` below and the import in
``core/models.py``). Do not add a separate app for them.

Mapping models translate internal TTR identifiers into the Channex UUIDs the
API requires. Nothing about Channex IDs is ever hardcoded in application code —
it is always resolved through these tables (see ``core/ota/mapping.py``).

ARIChange is the outbound outbox: every availability / rate / restriction change
records a row here, and a background worker (WS-C) coalesces + batches + pushes
them to Channex with retry/backoff.
"""

import uuid

from django.db import models
from django.utils import timezone


ROOM_TYPE_CHOICES = [
    ("single", "Single"),
    ("double", "Double"),
    ("deluxe", "Deluxe"),
]


class ChannexProperty(models.Model):
    """Maps a TTR ``rooms.Property`` to its Channex property UUID."""

    objects = models.Manager()

    # Type annotations for static typing / Pyrefly (reverse relations)
    room_type_mappings: models.Manager
    ari_changes: models.Manager

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.OneToOneField(
        "rooms.Property",
        on_delete=models.CASCADE,
        related_name="channex_mapping",
    )
    channex_property_id = models.UUIDField(
        help_text="Property UUID as it exists in Channex.",
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="ISO 4217 currency code Channex expects for this property "
        "(the staging test property is USD; production is likely INR).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="If off, no ARI changes are recorded or pushed for this property.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        verbose_name = "Channex property mapping"
        verbose_name_plural = "Channex property mappings"

    def __str__(self):
        return f"{self.property} ↔ Channex {self.channex_property_id}"


class ChannexRoomType(models.Model):
    """Maps an internal room-type string (single/double/deluxe) for a property
    to a Channex room-type UUID. Several physical Rooms of the same type roll up
    into one Channex room type."""

    objects = models.Manager()

    rate_plans: models.Manager

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property_mapping = models.ForeignKey(
        ChannexProperty,
        on_delete=models.CASCADE,
        related_name="room_type_mappings",
    )
    room_type = models.CharField(max_length=10, choices=ROOM_TYPE_CHOICES)
    channex_room_type_id = models.UUIDField(
        help_text="Room type UUID as it exists in Channex.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        verbose_name = "Channex room-type mapping"
        verbose_name_plural = "Channex room-type mappings"
        constraints = [
            models.UniqueConstraint(
                fields=["property_mapping", "room_type"],
                name="uniq_channex_roomtype_per_property",
            ),
        ]

    def __str__(self):
        return f"{self.property_mapping.property} / {self.room_type} ↔ {self.channex_room_type_id}"


class ChannexRatePlan(models.Model):
    """Maps a rate plan under a room type to its Channex rate-plan UUID.

    This is a one-to-many: a room type may carry one plan (e.g. Best Available
    Rate) or several (BAR + Bed & Breakfast). Rates and restrictions attach to a
    rate plan in Channex, so every push needs one of these."""

    objects = models.Manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_type_mapping = models.ForeignKey(
        ChannexRoomType,
        on_delete=models.CASCADE,
        related_name="rate_plans",
    )
    name = models.CharField(
        max_length=100,
        default="Best Available Rate",
        help_text="Human label for this rate plan (e.g. 'BAR', 'Bed & Breakfast').",
    )
    channex_rate_plan_id = models.UUIDField(
        help_text="Rate plan UUID as it exists in Channex.",
    )
    is_default = models.BooleanField(
        default=True,
        help_text="The plan used when a change does not name a specific rate plan.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        verbose_name = "Channex rate-plan mapping"
        verbose_name_plural = "Channex rate-plan mappings"

    def __str__(self):
        return f"{self.name} ↔ {self.channex_rate_plan_id}"


class ARIChange(models.Model):
    """Outbound outbox row.

    Every code path that mutates availability / rates / restrictions records a
    row here via ``core.ota.dispatch.record_ari_change``. The WS-C worker
    (``core.ota.tasks.process_ari_outbox``) coalesces pending rows by
    (property, change_type, room_type), batches date ranges, resolves Channex
    UUIDs, and pushes — retrying 429/5xx with backoff. Nothing calls the Channex
    API directly from a view or service."""

    objects = models.Manager()

    CHANGE_AVAILABILITY = "availability"
    CHANGE_RATES = "rates"
    CHANGE_RESTRICTIONS = "restrictions"
    CHANGE_TYPE_CHOICES = [
        (CHANGE_AVAILABILITY, "Availability"),
        (CHANGE_RATES, "Rates"),
        (CHANGE_RESTRICTIONS, "Restrictions"),
    ]

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property_mapping = models.ForeignKey(
        ChannexProperty,
        on_delete=models.CASCADE,
        related_name="ari_changes",
    )
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPE_CHOICES)
    room_type = models.CharField(
        max_length=10,
        help_text="Internal room-type string; resolved to a Channex UUID at push time.",
    )
    date_from = models.DateField()
    date_to = models.DateField(help_text="Exclusive end date of the affected range.")
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    retry_count = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(
        default=timezone.now,
        help_text="Worker skips this row until now >= next_retry_at (backoff).",
    )
    channex_task_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Task/response id returned by Channex on a successful push "
        "(used as evidence for certification).",
    )
    error_detail = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        verbose_name = "ARI change (outbox)"
        verbose_name_plural = "ARI changes (outbox)"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "next_retry_at"], name="idx_arichange_status_retry"),
        ]

    def __str__(self):
        return f"{self.change_type} {self.room_type} {self.date_from}..{self.date_to} [{self.status}]"
