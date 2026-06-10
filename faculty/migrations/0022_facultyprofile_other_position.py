from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0021_facultyclearancerequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='facultyprofile',
            name='other_position',
            field=models.CharField(
                blank=True,
                max_length=255,
                help_text='Optional title/position used in exports (e.g. Program Chair, Campus Director).',
            ),
        ),
    ]
