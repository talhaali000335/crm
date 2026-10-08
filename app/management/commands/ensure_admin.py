import os, secrets
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Create the first user from ADMIN_USERNAME/ADMIN_PASSWORD (random password printed if unset)."
    def handle(self, *a, **k):
        U = get_user_model()
        if U.objects.exists(): return
        user = os.getenv("ADMIN_USERNAME", "admin")
        pw = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(10)
        U.objects.create_superuser(user, "", pw)
        self.stdout.write(f"ADMIN LOGIN -> username: {user}  password: {pw}")
