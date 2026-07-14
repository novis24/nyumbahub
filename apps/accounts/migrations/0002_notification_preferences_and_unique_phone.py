from django.db import migrations, models
import phonenumber_field.modelfields


def clean_duplicate_phones(apps, schema_editor):
    User = apps.get_model('accounts', 'CustomUser')
    seen = set()
    for user in User.objects.exclude(phone__isnull=True).order_by('created_at', 'pk'):
        normalized = str(user.phone).strip()
        if not normalized or normalized in seen:
            user.phone = None
            user.save(update_fields=['phone'])
        else:
            seen.add(normalized)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0001_initial')]

    operations = [
        migrations.RunPython(clean_duplicate_phones, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='customuser',
            name='phone',
            field=phonenumber_field.modelfields.PhoneNumberField(
                blank=True, max_length=128, null=True, region='TZ', unique=True
            ),
        ),
        migrations.AddField(
            model_name='customuser',
            name='receives_push_notifications',
            field=models.BooleanField(default=False),
        ),
    ]
