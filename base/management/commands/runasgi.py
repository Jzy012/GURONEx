import os
import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run Daphne ASGI server for local development"

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
        parser.add_argument("--port", default="8000", help="Port to bind")

    def handle(self, *args, **options):
        host = str(options["host"])
        port = str(options["port"])

        app_target = "FEMS.asgi:application"
        command = [sys.executable, "-m", "daphne", "-b", host, "-p", port, app_target]

        self.stdout.write(self.style.SUCCESS(f"Starting ASGI server on {host}:{port}"))
        self.stdout.write("Command: " + " ".join(command))

        env = os.environ.copy()
        env.setdefault("DJANGO_SETTINGS_MODULE", "FEMS.settings")

        try:
            subprocess.run(command, check=True, env=env)
        except FileNotFoundError:
            self.stderr.write(
                self.style.ERROR(
                    "Daphne is not installed. Install it with: pip install daphne"
                )
            )
        except subprocess.CalledProcessError as exc:
            self.stderr.write(self.style.ERROR(f"Daphne exited with code {exc.returncode}"))
