from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from accounts.models import LoginAttempt, UserProfile
from accounts.utils import normalize_email


class Command(BaseCommand):
    help = "Create or repair a super admin account and clear its login locks."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Super admin email address.")
        parser.add_argument("--password", help="Password to set for the super admin.")
        parser.add_argument("--full-name", default="Super Admin", help="Full name for a new user.")
        parser.add_argument("--phone", default="", help="Phone number for a new user.")
        parser.add_argument(
            "--clear-cache",
            action="store_true",
            dest="clear_cache",
            help="Also clear the configured Django cache.",
        )

    def handle(self, *args, **options):
        email = normalize_email(options["email"])
        password = options.get("password")
        if not email:
            raise CommandError("--email is required.")

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "full_name": options["full_name"],
                "phone": options["phone"],
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )

        if password:
            user.set_password(password)
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        if not user.full_name:
            user.full_name = options["full_name"]
        user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = "super_admin"
        profile.must_change_password = False
        profile.save(update_fields=["role", "must_change_password"])

        cleared, _ = LoginAttempt.objects.filter(email=email).delete()
        if options.get("clear_cache"):
            cache.clear()
            self.stdout.write("Cache cleared.")

        action = "created" if created else "repaired"
        self.stdout.write(
            self.style.SUCCESS(
                f"Super admin ready: {email} ({action}); cleared {cleared} login lock row(s)."
            )
        )
