from django.db import migrations


def copy_property_rating_to_rooms(apps, schema_editor):
    """Copy each room's property.rating into room.rating where room.rating is NULL."""
    Room = apps.get_model('rooms', 'Room')
    for room in Room.objects.select_related('property').filter(rating__isnull=True):
        if room.property and room.property.rating is not None:
            room.rating = room.property.rating
        else:
            room.rating = 4.5  # default fallback
        room.save(update_fields=['rating'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('rooms', '0015_room_rating'),
    ]

    operations = [
        migrations.RunPython(copy_property_rating_to_rooms, noop),
    ]
