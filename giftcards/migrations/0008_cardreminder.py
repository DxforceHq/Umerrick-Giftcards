from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('giftcards', '0007_staff_permissions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CardReminder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stage', models.CharField(choices=[('FIRST', 'First reminder'), ('SECOND', 'Second reminder'), ('FINAL', 'Expiry reminder')], max_length=6)),
                ('sent_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('message', models.TextField()),
                ('card', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reminders', to='giftcards.giftcard')),
                ('sent_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='card_reminders_sent', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['sent_at']},
        ),
        migrations.AddConstraint(model_name='cardreminder', constraint=models.UniqueConstraint(fields=('card', 'stage'), name='unique_card_reminder_stage')),
    ]
