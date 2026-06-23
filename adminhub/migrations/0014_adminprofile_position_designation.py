from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('adminhub', '0013_adminprofile_contact_number_validator'),
    ]

    operations = [
        migrations.RenameField(
            model_name='adminprofile',
            old_name='other_position',
            new_name='designation',
        ),
        migrations.AddField(
            model_name='adminprofile',
            name='position',
            field=models.CharField(
                blank=True,
                default='',
                max_length=255,
                help_text='e.g. Director IV, Chief Administrative Officer',
            ),
            preserve_default=False,
        ),
    ]
