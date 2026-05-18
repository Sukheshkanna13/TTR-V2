from django.db import migrations, models


def promote_existing_portal_employees(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    UserProfile.objects.filter(role="employee").update(role="employee_admin")


def demote_employee_admins(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    UserProfile.objects.filter(role="employee_admin").update(role="employee")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_add_loyalty_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("guest", "Guest"),
                    ("employee", "Employee"),
                    ("employee_admin", "Employee Admin"),
                    ("super_admin", "Super Admin"),
                ],
                default="guest",
                max_length=20,
            ),
        ),
        migrations.RunPython(promote_existing_portal_employees, demote_employee_admins),
    ]
