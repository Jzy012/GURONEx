from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('applicant', '0017_contact_number_validation'),
    ]

    operations = [
        migrations.AddField(
            model_name='applicant',
            name='psych_test_instructions',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='applicant',
            name='contract_of_service_instructions',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='applicantsalaryrequirementconfig',
            name='instructions',
            field=models.TextField(blank=True),
        ),
    ]
