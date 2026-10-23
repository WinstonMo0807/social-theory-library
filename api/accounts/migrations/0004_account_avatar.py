from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_user_token_version")]
    operations = [migrations.CreateModel(name="AccountAvatar", fields=[
        ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True,
            related_name="account_avatar", serialize=False, to=settings.AUTH_USER_MODEL)),
        ("image_ciphertext", models.BinaryField(blank=True, default=bytes)),
        ("revision", models.PositiveIntegerField(default=1)),
        ("updated_at", models.DateTimeField(auto_now=True)),
    ])]
