from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('giftcards', '0006_priceitem_price_updated_at')]

    operations = [
        migrations.AddField(model_name='profile', name='can_activate_cards', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='profile', name='can_redeem_cards', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='profile', name='can_view_prices', field=models.BooleanField(default=True)),
    ]
