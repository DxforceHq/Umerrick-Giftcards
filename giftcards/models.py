import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone
class Profile(models.Model):
    class Role(models.TextChoices): ADMIN='ADMIN','Admin'; STAFF='STAFF','Staff'
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='profile')
    role=models.CharField(max_length=8,choices=Role.choices,default=Role.STAFF)
    must_change_password=models.BooleanField(default=True)
    can_activate_cards=models.BooleanField(default=True)
    can_redeem_cards=models.BooleanField(default=True)
    can_view_prices=models.BooleanField(default=True)

class PriceItem(models.Model):
    name=models.CharField(max_length=180,db_index=True)
    price=models.DecimalField(max_digits=12,decimal_places=2)
    is_active=models.BooleanField(default=True,db_index=True)
    updated_at=models.DateTimeField(auto_now=True)
    price_updated_at=models.DateTimeField(default=timezone.now)
    updated_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='updated_price_items')
    class Meta:
        ordering=['name','pk']
        constraints=[models.CheckConstraint(condition=models.Q(price__gte=0),name='price_item_nonnegative')]
    def __str__(self): return self.name
class GiftCard(models.Model):
    class Kind(models.TextChoices): N10='N10','₦10,000'; N15='N15','₦15,000'; PCT10='PCT10','10%'
    class Status(models.TextChoices): GENERATED='GENERATED','Generated'; ACTIVE='ACTIVE','Active'; REDEEMED='REDEEMED','Redeemed'; CANCELLED='CANCELLED','Cancelled'
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    code=models.CharField(max_length=19,unique=True,db_index=True)
    kind=models.CharField(max_length=5,choices=Kind.choices)
    status=models.CharField(max_length=10,choices=Status.choices,default=Status.GENERATED,db_index=True)
    created_at=models.DateTimeField(default=timezone.now,editable=False)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='generated_cards')
    activated_at=models.DateTimeField(null=True,blank=True)
    activated_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name='activated_cards')
    customer_phone=models.CharField(max_length=20,blank=True)
    activation_purchase_amount=models.DecimalField(max_digits=12,decimal_places=2,null=True,blank=True)
    expires_at=models.DateTimeField(null=True,blank=True)
    redeemed_at=models.DateTimeField(null=True,blank=True)
    redeemed_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name='redeemed_cards')
    batch_id=models.UUIDField(default=uuid.uuid4,db_index=True)
    class Meta:
        ordering=['-created_at']; indexes=[models.Index(fields=['status','kind','created_at'])]
        constraints=[models.CheckConstraint(condition=models.Q(activation_purchase_amount__gte=0)|models.Q(activation_purchase_amount__isnull=True),name='activation_purchase_nonnegative')]
    def __str__(self): return f'{self.get_kind_display()} · {self.code}'
    @property
    def value(self): return Decimal('10000.00') if self.kind==self.Kind.N10 else Decimal('15000.00') if self.kind==self.Kind.N15 else None
    @property
    def eligible_at(self): return self.activated_at+timezone.timedelta(hours=72) if self.activated_at else None
    @property
    def display_status(self):
        now=timezone.now()
        if self.status==self.Status.ACTIVE and self.expires_at and now>=self.expires_at: return 'EXPIRED'
        if self.status==self.Status.ACTIVE and self.eligible_at and now<self.eligible_at: return 'WAITING'
        if self.status==self.Status.ACTIVE: return 'READY'
        return self.status
class Redemption(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    card=models.OneToOneField(GiftCard,on_delete=models.PROTECT,related_name='redemption')
    staff=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    purchase_amount=models.DecimalField(max_digits=12,decimal_places=2)
    discount_amount=models.DecimalField(max_digits=12,decimal_places=2)
    payable_amount=models.DecimalField(max_digits=12,decimal_places=2)
    created_at=models.DateTimeField(default=timezone.now)
    class Meta: constraints=[models.CheckConstraint(condition=models.Q(purchase_amount__gte=0)&models.Q(discount_amount__gte=0)&models.Q(payable_amount__gte=0),name='redemption_amounts_nonnegative')]
class AuditEvent(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    card=models.ForeignKey(GiftCard,null=True,blank=True,on_delete=models.PROTECT,related_name='events')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT)
    action=models.CharField(max_length=40,db_index=True)
    occurred_at=models.DateTimeField(default=timezone.now,db_index=True)
    previous_state=models.CharField(max_length=20,blank=True); new_state=models.CharField(max_length=20,blank=True)
    outcome=models.CharField(max_length=20); transaction_ref=models.UUIDField(null=True,blank=True)
    details=models.JSONField(default=dict,blank=True)
    class Meta: ordering=['-occurred_at']
    @property
    def recorded_purchase_amount(self):
        if self.outcome!='SUCCESS' or not self.card_id: return None
        if self.action=='ACTIVATION': return self.card.activation_purchase_amount
        if self.action=='REDEMPTION':
            redemption=getattr(self.card,'redemption',None)
            if redemption and (not self.transaction_ref or self.transaction_ref==redemption.pk):
                return redemption.purchase_amount
        return None
