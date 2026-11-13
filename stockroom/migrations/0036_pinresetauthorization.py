from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('stockroom', '0035_duplicateloanauthorization'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PinResetAuthorization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_digest', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('credential', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pin_resets', to='stockroom.employeecredential')),
                ('issued_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='authorized_pin_resets', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at', '-pk']},
        ),
    ]
