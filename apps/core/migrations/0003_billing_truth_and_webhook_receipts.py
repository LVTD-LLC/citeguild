import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0002_initial")]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="stripe_cancel_at_period_end",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="profile",
            name="stripe_current_period_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="stripe_last_event_created",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="profile",
            name="stripe_last_event_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="profile",
            name="stripe_subscription_status",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.CreateModel(
            name="StripeWebhookEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event_id", models.CharField(max_length=255, unique=True)),
                ("event_type", models.CharField(max_length=255)),
                ("event_created", models.PositiveBigIntegerField(default=0)),
                ("outcome", models.CharField(default="processed", max_length=32)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
