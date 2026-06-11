from django.db import migrations

INITIAL_EXTENSIONS = [
    'pdf',
    'doc',
    'docx',
    'xls',
    'xlsx',
    'ppt',
    'pptx',
    'jpg',
    'jpeg',
    'png',
]


def seed_file_types(apps, schema_editor):
    FileType = apps.get_model('faculty', 'FileType')
    for ext in INITIAL_EXTENSIONS:
        FileType.objects.get_or_create(extension=ext)


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0022_facultyprofile_other_position'),
    ]

    operations = [
        migrations.RunPython(seed_file_types, migrations.RunPython.noop),
    ]
