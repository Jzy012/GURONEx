from django.db import migrations, models
import faculty.models


class Migration(migrations.Migration):

    dependencies = [
        ('adminhub', '0012_adminprofile_other_position'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminprofile',
            name='contact_number',
            field=models.CharField(
                blank=True,
                max_length=11,
                null=True,
                validators=[faculty.models.phone_validator],
            ),
        ),
    ]
