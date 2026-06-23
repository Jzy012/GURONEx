from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faculty', '0023_seed_initial_file_types'),
    ]

    operations = [
        migrations.RenameField(
            model_name='facultyprofile',
            old_name='other_position',
            new_name='designation',
        ),
        migrations.AddField(
            model_name='facultyprofile',
            name='position',
            field=models.CharField(
                blank=True,
                default='',
                max_length=255,
                help_text='e.g. Instructor II, Assistant Professor I',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='facultyprofile',
            name='personal_email',
            field=models.EmailField(
                blank=True,
                null=True,
                help_text='Secondary email address used for notifications.',
            ),
        ),
        migrations.AlterField(
            model_name='facultyprofile',
            name='department',
            field=models.CharField(
                max_length=100,
                null=True,
                blank=True,
                default='San Pedro Campus',
            ),
        ),
    ]
