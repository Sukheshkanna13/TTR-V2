from django.core.cache import cache
from django.core.management.base import BaseCommand

from accounts.models import LoginAttempt
from accounts.utils import normalize_email


class Command(BaseCommand):
    help = "Clear login lock rows, optionally for one email, and optionally clear cache."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Clear login locks only for this email address.")
        parser.add_argument(
            "--clear-cache",
            action="store_true",
            dest="clear_cache",
            help="Also clear the configured Django cache.",
        )

    def handle(self, *args, **options):
        email = normalize_email(options.get("email"))
        queryset = LoginAttempt.objects.all()
        if email:
            queryset = queryset.filter(email=email)

        count = queryset.count()
        queryset.delete()

        if options.get("clear_cache"):
            cache.clear()
            self.stdout.write("Cache cleared.")

        label = "login lock" if count == 1 else "login locks"
        scope = f" for {email}" if email else ""
        self.stdout.write(self.style.SUCCESS(f"Cleared {count} {label}{scope}."))
