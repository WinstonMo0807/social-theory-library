import secrets

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ReaderProfile, User


@receiver(post_save, sender=User)
def ensure_reader_profile(sender, instance, created, **kwargs):
    if created:
        ReaderProfile.objects.get_or_create(
            user=instance,
            defaults={"recommendation_seed": secrets.token_hex(16)},
        )
