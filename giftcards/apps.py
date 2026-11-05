from django.apps import AppConfig
class GiftcardsConfig(AppConfig):
    default_auto_field='django.db.models.BigAutoField'; name='giftcards'
    def ready(self): from . import signals
