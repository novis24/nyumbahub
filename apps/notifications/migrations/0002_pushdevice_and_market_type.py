from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification', name='notification_type',
            field=models.CharField(
                choices=[('listing_approved', 'Listing Approved'), ('listing_expired', 'Listing Expired'),
                         ('sub_expiring', 'Subscription Expiring'), ('sub_renewed', 'Subscription Renewed'),
                         ('kyc_approved', 'Verification Approved'), ('kyc_rejected', 'Verification Rejected'),
                         ('new_inquiry', 'New Inquiry'), ('system', 'System Message'),
                         ('new_market_listing', 'New Marketplace Listing')],
                default='system', max_length=30,
            ),
        ),
        migrations.CreateModel(
            name='PushDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.TextField(unique=True)), ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='push_devices', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
