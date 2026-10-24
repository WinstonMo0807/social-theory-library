from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_account_avatar")]
    operations = [
        migrations.AddField(model_name="recoverycode", name="purpose", field=models.CharField(
            choices=[("password_code", "旧密码验证码"), ("password_link", "密码恢复链接"), ("verify_email", "验证邮箱")],
            default="password_code", max_length=20)),
        migrations.AddField(model_name="recoverycode", name="account_fingerprint",
            field=models.CharField(blank=True, default="", max_length=64)),
    ]
