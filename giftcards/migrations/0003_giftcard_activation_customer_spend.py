from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('giftcards', '0002_audit_immutable')]

    operations = [
        migrations.AddField(
            model_name='giftcard',
            name='customer_phone',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='giftcard',
            name='activation_purchase_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddConstraint(
            model_name='giftcard',
            constraint=models.CheckConstraint(
                condition=models.Q(activation_purchase_amount__gte=0) | models.Q(activation_purchase_amount__isnull=True),
                name='activation_purchase_nonnegative',
            ),
        ),
    ]
