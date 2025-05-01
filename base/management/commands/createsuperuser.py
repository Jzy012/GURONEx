from django.contrib.auth.management.commands import createsuperuser
from django.core.management import CommandError
from base.models import Account

class Command(createsuperuser.Command):
    def handle(self, *args, **options):
        # Set the role for superuser as 'system_admin'
        options['role'] = 'system_admin'
        super().handle(*args, **options)
