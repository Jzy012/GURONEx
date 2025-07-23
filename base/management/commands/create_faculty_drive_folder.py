from django.core.management.base import BaseCommand
from faculty.models import FacultyProfile
from services.google_drive_service import CentralGoogleDriveService
from base.models import Account  # or wherever your user model is

class Command(BaseCommand):
    help = 'Create and link Google Drive folder for a faculty profile using OAuth'

    def add_arguments(self, parser):
        parser.add_argument('faculty_id', type=int)
        parser.add_argument('--share-with', type=str, help='Google email to share the folder with')

    def handle(self, *args, **kwargs):
        faculty_id = kwargs['faculty_id']
        share_with = kwargs.get('share_with')

        try:
            faculty = FacultyProfile.objects.get(id=faculty_id)
        except FacultyProfile.DoesNotExist:
            return self.stdout.write(self.style.ERROR("❌ Faculty not found"))

        try:
            drive = CentralGoogleDriveService() # OAuth2 only
            folder_id = drive.create_faculty_folder(faculty)

            faculty.gdrive_folder_id = folder_id
            faculty.save()

            if share_with:
                drive.share_folder_with_user(folder_id, share_with)

            self.stdout.write(self.style.SUCCESS(f"✅ Folder created and linked: {folder_id}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {str(e)}"))
