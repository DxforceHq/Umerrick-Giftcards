from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Profile
@receiver(post_save,sender='auth.User')
def ensure_profile(sender,instance,created,**kwargs):
    if created: Profile.objects.create(user=instance,role=Profile.Role.ADMIN if instance.is_superuser else Profile.Role.STAFF,must_change_password=not instance.is_superuser)
