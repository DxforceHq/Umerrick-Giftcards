from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('giftcards', '0008_cardreminder')]

    operations = [
        migrations.AddField(
            model_name='giftcard',
            name='reminder_short_url',
            field=models.URLField(blank=True, max_length=255),
        ),
    ]
