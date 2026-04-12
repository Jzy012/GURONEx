from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('adminhub', '0009_announcement_schedule_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceFeatureSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enable_faculty_manual_attendance', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Attendance Feature Setting',
                'verbose_name_plural': 'Attendance Feature Setting',
            },
        ),
    ]
