from django.db import migrations


def fix_needs_cleaning(apps, schema_editor):
    """
    auto_complete_bookings used to write operational_status='needs_cleaning',
    which is not a valid Room.OPERATIONAL_STATUS_CHOICES value. The valid
    value is 'cleaning'.
    """
    Room = apps.get_model("rooms", "Room")
    Room.objects.filter(operational_status="needs_cleaning").update(
        operational_status="cleaning"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0024_roomrate_closed_to_arrival_and_more"),
    ]

    operations = [
        migrations.RunPython(fix_needs_cleaning, migrations.RunPython.noop),
    ]
