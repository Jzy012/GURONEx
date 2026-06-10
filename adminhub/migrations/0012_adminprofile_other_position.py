from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('adminhub', '0011_registrationsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='adminprofile',
            name='other_position',
            field=models.CharField(
                blank=True,
                max_length=255,
                help_text='Optional title/position used in exports (e.g. HR Coordinator, Guidance Coordinator).',
            ),
        ),
    ]
