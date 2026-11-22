from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('giftcards', '0009_giftcard_reminder_short_url')]

    operations = [
        migrations.AddField(
            model_name='giftcard',
            name='is_test',
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
