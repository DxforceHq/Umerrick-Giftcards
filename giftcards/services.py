from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import secrets
import re
from django.db import IntegrityError, transaction
from django.db.models.functions import Now
from django.utils import timezone
from .models import GiftCard, Redemption, AuditEvent
ALPHABET='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
def database_now():
    value=GiftCard.objects.order_by().annotate(_db_now=Now()).values_list('_db_now',flat=True).first()
    return value or timezone.now()
def new_code():
    raw=''.join(secrets.choice(ALPHABET) for _ in range(16))
    return '-'.join(raw[i:i+4] for i in range(0,16,4))
def generate_cards(actor,kind,count):
    if kind not in GiftCard.Kind.values: raise ValueError('Choose a valid card type.')
    if not 1<=count<=500: raise ValueError('Generate between 1 and 500 cards per batch.')
    batch=secrets.token_hex(16); created=[]
    with transaction.atomic():
        for _ in range(count):
            for attempt in range(5):
                try:
                    with transaction.atomic(): card=GiftCard.objects.create(code=new_code(),kind=kind,created_by=actor,batch_id=batch)
                    created.append(card); break
                except IntegrityError:
                    if attempt==4: raise
    return created
def card_discount(card,amount):
    try: purchase=Decimal(str(amount)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    except (InvalidOperation,ValueError): raise ValueError('Enter a valid purchase amount.')
    if not purchase.is_finite() or purchase<=0 or purchase>Decimal('99999999.99'): raise ValueError('Purchase must be greater than zero and within the supported range.')
    discount=min(purchase,card.value) if card.kind in (GiftCard.Kind.N10,GiftCard.Kind.N15) else (purchase*Decimal('.10')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    return purchase,discount,(purchase-discount).quantize(Decimal('.01'))
def normalize_customer_phone(value):
    if value is None or value=='': return ''
    if not isinstance(value,str): raise ValueError('Enter exactly 10 digits after +234.')
    raw=value.strip()
    if not raw: return ''
    digits=raw[4:] if raw.startswith('+234') else raw
    if not re.fullmatch(r'[0-9]{10}',digits):
        raise ValueError('Enter exactly 10 digits after +234.')
    return '+234'+digits

def activation_spend(value):
    if value is None or value=='': return None
    if isinstance(value,bool): raise ValueError('Enter a valid amount spent at activation.')
    try:
        amount=Decimal(str(value).strip())
        cents=amount.quantize(Decimal('.01'))
    except (InvalidOperation,ValueError):
        raise ValueError('Enter a valid amount spent at activation.')
    if not amount.is_finite() or amount<0 or amount>Decimal('9999999999.99') or amount!=cents:
        raise ValueError('Enter an amount from ₦0 to ₦9,999,999,999.99 with at most two decimal places.')
    return cents

def activate(card_id,actor,customer_phone='',activation_purchase_amount=None):
    failure=None; result=None
    with transaction.atomic():
        card=GiftCard.objects.select_for_update().get(pk=card_id); previous=card.status
        if previous!=GiftCard.Status.GENERATED:
            failure=f'This card cannot be activated in its current state ({card.display_status}).'
            reason_code='NOT_GENERATED'
        else:
            try:
                phone=normalize_customer_phone(customer_phone)
                if not phone:
                    raise ValueError('Enter the customer phone number: 10 digits after +234.')
                spent=activation_spend(activation_purchase_amount)
            except ValueError as exc:
                failure=str(exc); reason_code='INVALID_ACTIVATION_DETAILS'
        if failure:
            AuditEvent.objects.create(card=card,actor=actor,action='ACTIVATION',previous_state=previous,new_state=previous,outcome='REJECTED',details={'reason':failure,'reason_code':reason_code})
        else:
            now=database_now(); card.status=GiftCard.Status.ACTIVE; card.activated_at=now; card.expires_at=now+timezone.timedelta(days=60); card.activated_by=actor
            card.customer_phone=phone; card.activation_purchase_amount=spent
            card.save(update_fields=['status','activated_at','expires_at','activated_by','customer_phone','activation_purchase_amount'])
            AuditEvent.objects.create(card=card,actor=actor,action='ACTIVATION',previous_state=previous,new_state=card.status,outcome='SUCCESS'); result=card
    if failure: raise ValueError(failure)
    return result
def redeem(card_id,actor,amount):
    failure=None; result=None
    with transaction.atomic():
        card=GiftCard.objects.select_for_update().get(pk=card_id); previous=card.display_status; now=database_now()
        reason_code=''
        if card.status!=GiftCard.Status.ACTIVE:
            failure='This card is not active or has already been redeemed.'
            reason_code='ALREADY_REDEEMED' if card.status==GiftCard.Status.REDEEMED else 'NOT_ACTIVE'
        elif card.expires_at is None or now>=card.expires_at: failure='This card has expired.'; reason_code='EXPIRED_CARD'
        elif card.activated_at is None or now<card.activated_at+timezone.timedelta(hours=72): failure='This card is still in its 72-hour activation waiting period.'; reason_code='WAITING_PERIOD'
        else:
            try: purchase,discount,payable=card_discount(card,amount)
            except ValueError as exc: failure=str(exc); reason_code='INVALID_PURCHASE'
        if failure:
            AuditEvent.objects.create(card=card,actor=actor,action='REDEMPTION',previous_state=previous,new_state=previous,outcome='REJECTED',details={'reason':failure,'reason_code':reason_code})
        else:
            record=Redemption.objects.create(card=card,staff=actor,purchase_amount=purchase,discount_amount=discount,payable_amount=payable)
            card.status=GiftCard.Status.REDEEMED; card.redeemed_at=now; card.redeemed_by=actor; card.save(update_fields=['status','redeemed_at','redeemed_by'])
            AuditEvent.objects.create(card=card,actor=actor,action='REDEMPTION',previous_state=previous,new_state=card.status,outcome='SUCCESS',transaction_ref=record.id,details={'purchase_amount':str(purchase),'discount_amount':str(discount),'payable_amount':str(payable)}); result=record
    if failure: raise ValueError(failure)
    return result
