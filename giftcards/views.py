import base64, hashlib, io, json, re, uuid
from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urlencode, urlparse
from django.conf import settings
from django.core.cache import cache
from django.core import signing
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.db.models import Count, Min, Q
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from .forms import GenerateForm, StaffCreateForm, StaffPermissionsForm, PriceItemForm
from .models import AuditEvent, GiftCard, Profile, Redemption, PriceItem
from .permissions import role_required, staff_can
from .services import generate_cards, activate, redeem, card_discount, database_now, normalize_customer_phone

def request_json(request):
    try: data=json.loads(request.body or '{}')
    except json.JSONDecodeError: raise ValueError('Malformed request.')
    if not isinstance(data,dict): raise ValueError('Malformed request.')
    return data

QR_SIGNING_SALT='umerrick.gift-card.qr'

def qr_payload(request, card):
    """Build a signed QR payload on the server; the browser never creates it."""
    token=signing.Signer(salt=QR_SIGNING_SALT).sign(str(card.id))
    return request.build_absolute_uri(f"{reverse('scanner')}?{urlencode({'token':token})}")

def card_from_qr_payload(payload):
    """Verify a scanned QR payload before any gift card lookup occurs."""
    if not isinstance(payload,str) or not payload or len(payload)>2048:
        return None
    parsed=urlparse(payload)
    params=parse_qs(parsed.query)
    try:
        if 'token' in params:
            if parsed.path!=reverse('scanner') or set(params)!={'token'} or len(params['token'])!=1:
                return None
            card_id=uuid.UUID(signing.Signer(salt=QR_SIGNING_SALT).unsign(params['token'][0]))
        elif set(params)=={'card'} and parsed.path==reverse('scanner') and len(params['card'])==1:
            # QR cards printed before signatures were introduced remain usable.
            card_id=uuid.UUID(params['card'][0])
        else:
            return None
    except (signing.BadSignature, ValueError):
        return None
    return GiftCard.objects.filter(pk=card_id).first()
def is_admin(user): return user.is_superuser or getattr(getattr(user,'profile',None),'role','')==Profile.Role.ADMIN

@role_required('ADMIN','STAFF',permission='can_view_prices')
def prices_view(request):
    if request.method!='GET': return HttpResponse(status=405)
    admin_access=is_admin(request.user)
    response=render(request,'giftcards/prices.html',{
        'admin_access':admin_access,
        'items':PriceItem.objects.all() if admin_access else PriceItem.objects.filter(is_active=True),
        'form':PriceItemForm() if admin_access else None,
    })
    if not admin_access: response['X-Price-Offline']='staff'
    return response

@role_required('ADMIN','STAFF',permission='can_view_prices')
def prices_data(request):
    if request.method!='GET': return HttpResponse(status=405)
    items=PriceItem.objects.filter(is_active=True).order_by('name','pk')
    return JsonResponse({'items':[{'name':item.name.title(),'price':str(item.price),'updated_at':item.price_updated_at.isoformat()}
                                  for item in items], 'synced_at':timezone.now().isoformat()})

@role_required('ADMIN')
@require_POST
def price_create(request):
    names=request.POST.getlist('name')
    prices=request.POST.getlist('price')
    if not names or len(names)!=len(prices) or len(names)>100:
        messages.error(request,'Add between 1 and 100 complete items at a time.')
        return redirect('prices')
    existing={name.casefold() for name in PriceItem.objects.values_list('name',flat=True)}
    added=0; duplicates=[]; invalid=[]
    with transaction.atomic():
        for row_number,(name,price) in enumerate(zip(names,prices),start=1):
            normalized=' '.join(name.split()).title()
            key=normalized.casefold()
            if key and key in existing:
                duplicates.append(normalized)
                continue
            form=PriceItemForm({'name':name,'price':price})
            if not form.is_valid():
                invalid.append(row_number)
                continue
            item=form.save(commit=False); item.updated_by=request.user; item.save()
            existing.add(key); added+=1
    if added:
        messages.success(request,f'{added} item{"s" if added!=1 else ""} added to the price list.')
    if duplicates:
        examples=', '.join(duplicates[:3])
        suffix='…' if len(duplicates)>3 else ''
        messages.warning(request,f'{len(duplicates)} duplicate item{"s" if len(duplicates)!=1 else ""} skipped: {examples}{suffix}.')
    if invalid:
        rows=', '.join(str(row) for row in invalid[:5])
        suffix='…' if len(invalid)>5 else ''
        messages.warning(request,f'{len(invalid)} invalid row{"s" if len(invalid)!=1 else ""} skipped (row {rows}{suffix}). Check the name and price.')
    return redirect('prices')

@role_required('ADMIN')
@require_POST
def price_update(request,item_id):
    item=get_object_or_404(PriceItem,pk=item_id)
    form=PriceItemForm(request.POST,instance=item)
    if form.is_valid():
        price_changed='price' in form.changed_data
        item=form.save(commit=False); item.updated_by=request.user; item.save()
        if price_changed:
            item.price_updated_at=item.updated_at
            item.save(update_fields=['price_updated_at'])
        messages.success(request,'Price list item updated.')
    else: messages.error(request,'Check the item name and price. Names must be unique and prices cannot be negative.')
    return redirect('prices')

@role_required('ADMIN')
@require_POST
def price_toggle(request,item_id):
    item=get_object_or_404(PriceItem,pk=item_id)
    item.is_active=not item.is_active; item.updated_by=request.user
    item.save(update_fields=['is_active','updated_by','updated_at'])
    messages.success(request,'Item restored.' if item.is_active else 'Item made inactive.')
    return redirect('prices')
CARD_AUDIT_ACTIONS=('ACTIVATION','REDEMPTION')

def filter_local_dates(queryset, field, start=None, end=None):
    """Filter local calendar dates with UTC instants, without database date casts."""
    local_zone=ZoneInfo(settings.TIME_ZONE)
    if start:
        lower=datetime.combine(start,time.min,tzinfo=local_zone).astimezone(datetime_timezone.utc)
        queryset=queryset.filter(**{f'{field}__gte':lower})
    if end:
        upper=datetime.combine(end+timedelta(days=1),time.min,tzinfo=local_zone).astimezone(datetime_timezone.utc)
        queryset=queryset.filter(**{f'{field}__lt':upper})
    return queryset

def dashboard_period(request):
    """Return an inclusive date window in the application's local timezone."""
    today=timezone.localdate()
    period=request.GET.get('period','30d')
    if period=='7d': start=today-timedelta(days=6)
    elif period=='90d': start=today-timedelta(days=89)
    elif period=='this_month': start=today.replace(day=1)
    elif period=='custom' or ('period' not in request.GET and ('from' in request.GET or 'to' in request.GET)):
        period='custom'
        try:
            start=date.fromisoformat(request.GET.get('from',''))
            end=date.fromisoformat(request.GET.get('to',''))
            if start>end or end>today:
                raise ValueError
            return period,start,end,''
        except ValueError:
            return '30d',today-timedelta(days=29),today,'Enter a valid date range ending no later than today.'
    else:
        period='30d'; start=today-timedelta(days=29)
    return period,start,today,''

def activity_chart(start,end):
    """Aggregate actual card timestamps into daily, weekly, or monthly buckets."""
    span=(end-start).days+1
    interval='day' if span<=31 else 'week' if span<=180 else 'month'
    def bucket(day):
        if interval=='day': return day
        if interval=='week': return start+timedelta(days=((day-start).days//7)*7)
        return day.replace(day=1)
    first=bucket(start)
    keys=[]; cursor=first
    while cursor<=end:
        keys.append(cursor)
        if interval=='day': cursor+=timedelta(days=1)
        elif interval=='week': cursor+=timedelta(days=7)
        else: cursor=date(cursor.year+1,1,1) if cursor.month==12 else date(cursor.year,cursor.month+1,1)
    counts={key:{'issued':0,'activated':0,'redeemed':0} for key in keys}
    for name,field in [('issued','created_at'),('activated','activated_at'),('redeemed','redeemed_at')]:
        rows=filter_local_dates(GiftCard.objects.all(),field,start,end).values_list(field,flat=True)
        for timestamp in rows.iterator():
            if timestamp is not None:
                day=timezone.localtime(timestamp,ZoneInfo(settings.TIME_ZONE)).date()
                counts[bucket(day)][name]+=1
    labels=[(f'{key:%b} {key.day}' if interval!='month' else f'{key:%b %Y}') for key in keys]
    return {'interval':interval,'labels':labels,'issued':[counts[key]['issued'] for key in keys],
            'activated':[counts[key]['activated'] for key in keys],
            'redeemed':[counts[key]['redeemed'] for key in keys]}

@role_required('ADMIN','STAFF')
def dashboard(request):
    show_install_prompt=request.session.pop('offer_home_screen_install',False)
    if is_admin(request.user):
        period,start,end,period_error=dashboard_period(request)
        cards=filter_local_dates(GiftCard.objects.all(),'created_at',start,end)
        stats={s:0 for s in ['GENERATED','WAITING','READY','REDEEMED','EXPIRED','CANCELLED']}
        for card in cards.iterator(): stats[card.display_status]+=1
        stats['TOTAL']=cards.count()
        recent=(filter_local_dates(AuditEvent.objects.filter(action__in=CARD_AUDIT_ACTIONS),
                                   'occurred_at',start,end).select_related('actor','card'))
        performance=[]
        staff=User.objects.filter(Q(profile__role__in=(Profile.Role.STAFF,Profile.Role.ADMIN))|Q(is_superuser=True)).select_related('profile').annotate(
            total_activated=Count('activated_cards',distinct=True),
            total_redeemed=Count('activated_cards',filter=Q(activated_cards__status=GiftCard.Status.REDEEMED),distinct=True),
        ).order_by('username')
        for person in staff:
            person.redemption_rate=round(100*person.total_redeemed/person.total_activated,1) if person.total_activated else 0
            performance.append(person)
        return render(request,'giftcards/dashboard_admin.html',{'stats':stats,'recent':recent[:10],
            'staff_performance':performance,'show_install_prompt':show_install_prompt,
            'by_kind':cards.values('kind').annotate(total=Count('id')),'from_filter':start.isoformat(),
            'to_filter':end.isoformat(),'period':period,'period_error':period_error,
            'period_label':f'{start:%b} {start.day}, {start:%Y} – {end:%b} {end.day}, {end:%Y}',
            'chart':activity_chart(start,end)})
    return render(request,'giftcards/dashboard_staff.html',{'operations':AuditEvent.objects.filter(actor=request.user,action__in=CARD_AUDIT_ACTIONS).select_related('card')[:12],'show_install_prompt':show_install_prompt})
@role_required('ADMIN')
def generate_view(request):
    form=GenerateForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try: cards=generate_cards(request.user,form.cleaned_data['kind'],form.cleaned_data['count'])
        except ValueError as exc: form.add_error(None,str(exc))
        else: return render(request,'giftcards/print_cards.html',{'cards':cards,'created':True})
    batches=(GiftCard.objects.order_by()
             .values('batch_id','kind','created_by__username')
             .annotate(card_count=Count('id'),generated_at=Min('created_at'))
             .order_by('-generated_at'))
    batch_page=Paginator(batches,12).get_page(request.GET.get('page'))
    return render(request,'giftcards/generate.html',{'form':form,'batch_page':batch_page})
@role_required('ADMIN')
def cards_view(request):
    cards=GiftCard.objects.select_related('created_by','activated_by','redeemed_by').all()
    status=request.GET.get('status',''); kind=request.GET.get('kind',''); query=request.GET.get('q','')
    now=database_now()
    if status in ('GENERATED','REDEEMED','CANCELLED'): cards=cards.filter(status=status)
    elif status=='WAITING': cards=cards.filter(status='ACTIVE',activated_at__gt=now-timezone.timedelta(hours=72),expires_at__gt=now)
    elif status=='READY': cards=cards.filter(status='ACTIVE',activated_at__lte=now-timezone.timedelta(hours=72),expires_at__gt=now)
    elif status=='EXPIRED': cards=cards.filter(status='ACTIVE',expires_at__lte=now)
    if kind in GiftCard.Kind.values: cards=cards.filter(kind=kind)
    staff=request.GET.get('staff',''); start=request.GET.get('from',''); end=request.GET.get('to','')
    try: date.fromisoformat(start) if start else None
    except ValueError: start=''
    try: date.fromisoformat(end) if end else None
    except ValueError: end=''
    if staff.isdigit(): cards=cards.filter(activated_by_id=staff)
    cards=filter_local_dates(cards,'created_at',date.fromisoformat(start) if start else None,
                             date.fromisoformat(end) if end else None)
    if query:
        search=Q(code__icontains=query)|Q(customer_phone__icontains=query)
        phone_query=query[1:] if len(query)==11 and query.startswith('0') and query.isdigit() else query
        try: search|=Q(customer_phone=normalize_customer_phone(phone_query))
        except ValueError: pass
        cards=cards.filter(search)
    statuses=[('GENERATED','Generated'),('WAITING','Waiting'),('READY','Ready'),('REDEEMED','Redeemed'),('EXPIRED','Expired'),('CANCELLED','Cancelled')]
    return render(request,'giftcards/cards.html',{'cards':cards[:500],'statuses':statuses,'kinds':GiftCard.Kind.choices,'status_filter':status,'kind_filter':kind,'query':query,'staff':User.objects.filter(profile__role='STAFF'),'staff_filter':staff,'from_filter':start,'to_filter':end})
@role_required('ADMIN')
def card_detail(request,card_id):
    card=get_object_or_404(GiftCard.objects.select_related('created_by','activated_by','redeemed_by'),pk=card_id)
    return render(request,'giftcards/card_detail.html',{'card':card,'events':card.events.filter(action__in=CARD_AUDIT_ACTIONS).select_related('actor','card','card__redemption'),'redemption':getattr(card,'redemption',None)})
@role_required('ADMIN')
def batch_print(request,batch_id):
    cards=GiftCard.objects.filter(batch_id=batch_id)
    if not cards.exists(): raise Http404
    return render(request,'giftcards/print_cards.html',{'cards':cards,'created':False})
@role_required('ADMIN')
def card_print(request,card_id):
    card=get_object_or_404(GiftCard,pk=card_id)
    return render(request,'giftcards/print_cards.html',{'cards':[card],'created':False})
@role_required('ADMIN')
def card_qr(request,card_id):
    import qrcode
    card=get_object_or_404(GiftCard,pk=card_id)
    payload=qr_payload(request,card)
    image=qrcode.make(payload); buffer=io.BytesIO(); image.save(buffer,format='PNG')
    return HttpResponse(buffer.getvalue(),content_type='image/png')
@role_required('ADMIN','STAFF',any_permission=('can_activate_cards','can_redeem_cards'))
def staff_scanner(request): return render(request,'giftcards/scanner.html')

def scanner(request):
    """Keep existing printed /scan/ QR URLs useful to customers and staff."""
    if request.user.is_authenticated:
        return staff_scanner(request)
    token=request.GET.get('token','')
    destination=reverse('public_card_status')
    if token:
        destination+=f"?{urlencode({'token':token})}"
    return redirect(destination)

def public_card_status(request):
    card=None
    attempted=False
    invalid=False
    limited=False
    if request.method == 'POST' or request.GET.get('token'):
        attempted=True
        remote_address=request.META.get('REMOTE_ADDR','unknown')
        key='public-card-lookup:'+hashlib.sha256(remote_address.encode()).hexdigest()
        cache.add(key,0,300)
        try:
            limited=cache.incr(key)>30
        except ValueError:
            limited=True
        if not limited:
            if request.method == 'POST':
                qr_value=request.POST.get('qr')
                if qr_value is not None:
                    if isinstance(qr_value,str) and len(qr_value)<=2048 and 'token' in parse_qs(urlparse(qr_value).query):
                        card=card_from_qr_payload(qr_value)
                else:
                    code=str(request.POST.get('code','')).strip().upper()
                    if re.fullmatch(r'[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}',code):
                        card=GiftCard.objects.filter(code=code).first()
            else:
                token=request.GET.get('token','')
                if len(token)<=512:
                    card=card_from_qr_payload(f"{reverse('scanner')}?{urlencode({'token':token})}")
            invalid=card is None
    response=render(request,'giftcards/public_status.html',{
        'card':card,'attempted':attempted,'invalid':invalid,'limited':limited,
        'status':card.display_status if card else None,
    })
    response['Cache-Control']='no-store'
    response['Referrer-Policy']='no-referrer'
    response['X-Robots-Tag']='noindex, nofollow'
    return response

def gift_card_terms(request):
    return render(request, 'giftcards/terms.html')

def card_json(card):
    return {'id':str(card.id),'code':card.code,'kind':card.get_kind_display(),'status':card.display_status,'activated_at':card.activated_at.isoformat() if card.activated_at else None,'eligible_at':card.eligible_at.isoformat() if card.eligible_at else None,'expires_at':card.expires_at.isoformat() if card.expires_at else None,'value':str(card.value) if card.value is not None else None,'activation_purchase_amount':str(card.activation_purchase_amount) if card.activation_purchase_amount is not None else None,'server_now':database_now().isoformat()}
@role_required('ADMIN','STAFF',any_permission=('can_activate_cards','can_redeem_cards'))
@require_POST
def card_lookup(request):
    try: data=request_json(request)
    except ValueError as exc: return JsonResponse({'error':str(exc)},status=400)
    qr_payload_value=data.get('qr')
    if qr_payload_value is not None:
        card=card_from_qr_payload(qr_payload_value)
        if not card:
            return JsonResponse({'error':'This QR code is invalid or was not issued by U_MERRICK.'},status=400)
    else:
        code=str(data.get('code','')).strip().upper()
        import re
        if not re.fullmatch(r'[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}',code):
            return JsonResponse({'error':'Enter a gift code in the format XXXX-XXXX-XXXX-XXXX.'},status=400)
        card=GiftCard.objects.filter(code=code).first()
    if not card:
        return JsonResponse({'error':'No card matches that code.'},status=404)
    response=card_json(card)
    response['can_activate']=staff_can(request.user,'can_activate_cards')
    response['can_redeem']=staff_can(request.user,'can_redeem_cards')
    if card.status==GiftCard.Status.ACTIVE and card.expires_at and database_now()>=card.expires_at:
        reason='This card has expired.'
        AuditEvent.objects.create(card=card,actor=request.user,action='REDEMPTION',previous_state='EXPIRED',new_state='EXPIRED',outcome='REJECTED',details={'reason':reason,'reason_code':'EXPIRED_CARD','stage':'presentation','source':'qr' if qr_payload_value is not None else 'manual'})
        response['status']='EXPIRED'
        response['rejection_reason']=reason
    return JsonResponse(response)
@role_required('ADMIN','STAFF',permission='can_activate_cards')
@require_POST
def activate_view(request,card_id):
    try: data=request_json(request)
    except ValueError as exc:
        card=GiftCard.objects.filter(pk=card_id).first()
        previous=card.display_status if card else ''
        AuditEvent.objects.create(card=card,actor=request.user,action='ACTIVATION',previous_state=previous,new_state=previous,outcome='REJECTED',details={'reason':str(exc),'reason_code':'MALFORMED_REQUEST'})
        return JsonResponse({'error':str(exc)},status=400)
    try: card=activate(card_id,request.user,data.get('customer_phone',''),data.get('activation_purchase_amount'))
    except GiftCard.DoesNotExist:
        AuditEvent.objects.create(actor=request.user,action='ACTIVATION',outcome='REJECTED',details={'reason':'unknown card'})
        return JsonResponse({'error':'Card not found.'},status=404)
    except ValueError as exc: return JsonResponse({'error':str(exc)},status=409)
    return JsonResponse(card_json(card))
@role_required('ADMIN','STAFF',permission='can_redeem_cards')
@require_POST
def preview_redemption(request,card_id):
    card=GiftCard.objects.filter(pk=card_id).first()
    if not card:
        return JsonResponse({'error':'Card not found.'},status=404)
    try:
        now=database_now()
        if card.status!=GiftCard.Status.ACTIVE: raise ValueError('Card is not active or has already been redeemed.')
        if card.expires_at is None or now>=card.expires_at: raise ValueError('This card has expired.')
        if card.eligible_at is None or now<card.eligible_at: raise ValueError('This card is still in its 72-hour waiting period.')
        purchase,discount,payable=card_discount(card,request_json(request).get('amount'))
    except (ValueError,TypeError) as exc:
        return JsonResponse({'error':str(exc)},status=400)
    return JsonResponse({'purchase_amount':str(purchase),'discount_amount':str(discount),'payable_amount':str(payable),'card':card_json(card)})
@role_required('ADMIN','STAFF',permission='can_redeem_cards')
@require_POST
def redeem_view(request,card_id):
    try: data=request_json(request)
    except ValueError as exc:
        card=GiftCard.objects.filter(pk=card_id).first()
        AuditEvent.objects.create(card=card,actor=request.user,action='REDEMPTION',
                                  previous_state=card.display_status if card else '',new_state=card.status if card else '',outcome='REJECTED',details={'reason':str(exc)})
        return JsonResponse({'error':str(exc)},status=400)
    try: record=redeem(card_id,request.user,data.get('amount'))
    except GiftCard.DoesNotExist:
        AuditEvent.objects.create(actor=request.user,action='REDEMPTION',outcome='REJECTED',details={'reason':'unknown card'})
        return JsonResponse({'error':'Card not found.'},status=404)
    except (ValueError,TypeError) as exc:
        return JsonResponse({'error':str(exc)},status=409)
    return JsonResponse({'status':'REDEEMED','purchase_amount':str(record.purchase_amount),'discount_amount':str(record.discount_amount),'payable_amount':str(record.payable_amount)},status=201)
@role_required('ADMIN')
def staff_view(request):
    form=StaffCreateForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        user=User.objects.create_user(form.cleaned_data['username'],password=form.cleaned_data['password']); user.profile.role=Profile.Role.STAFF; user.profile.must_change_password=True
        for field in ('can_activate_cards','can_redeem_cards','can_view_prices'): setattr(user.profile,field,form.cleaned_data[field])
        user.profile.save()
        messages.success(request,f'Staff account {user.username} created. Share the initial password with them securely.')
        return redirect('staff')
    return render(request,'giftcards/staff.html',{'form':form,'staff':User.objects.filter(profile__role='STAFF').select_related('profile').order_by('username')})

@role_required('ADMIN')
@require_POST
def staff_permissions(request,user_id):
    user=get_object_or_404(User,pk=user_id,profile__role=Profile.Role.STAFF)
    form=StaffPermissionsForm(request.POST)
    if form.is_valid():
        for field in ('can_activate_cards','can_redeem_cards','can_view_prices'):
            setattr(user.profile,field,form.cleaned_data[field])
        user.profile.save(update_fields=['can_activate_cards','can_redeem_cards','can_view_prices'])
        messages.success(request,f'Permissions updated for {user.username}.')
    else: messages.error(request,'Could not update staff permissions.')
    return redirect('staff')
@role_required('ADMIN')
@require_POST
def staff_toggle(request,user_id):
    user=get_object_or_404(User,pk=user_id,profile__role='STAFF')
    if user==request.user: return HttpResponse('You cannot deactivate your own account.',status=400)
    user.is_active=not user.is_active; user.save(update_fields=['is_active'])
    return redirect('staff')
@role_required('ADMIN')
@require_POST
def staff_reset(request,user_id):
    user=get_object_or_404(User,pk=user_id,profile__role='STAFF'); new_password=request.POST.get('password','')
    from django.contrib.auth.password_validation import validate_password
    try: validate_password(new_password,user)
    except Exception as exc: messages.error(request,' '.join(exc.messages)); return redirect('staff')
    user.set_password(new_password); user.profile.must_change_password=True; user.profile.save(update_fields=['must_change_password']); user.save(update_fields=['password'])
    messages.success(request,'Staff password reset. They must change it after signing in.')
    return redirect('staff')
@login_required
def password_change(request):
    form=PasswordChangeForm(request.user,request.POST or None)
    if request.method=='POST' and form.is_valid():
        first_change=request.user.profile.must_change_password
        user=form.save(); user.profile.must_change_password=False; user.profile.save(update_fields=['must_change_password']); update_session_auth_hash(request,user)
        if first_change: request.session['offer_home_screen_install']=True
        messages.success(request,'Password updated.'); return redirect('dashboard')
    return render(request,'registration/password_change.html',{'form':form})
@role_required('ADMIN')
def audit_view(request):
    events=AuditEvent.objects.filter(action__in=CARD_AUDIT_ACTIONS).select_related('actor','card','card__redemption')
    action=request.GET.get('action',''); outcome=request.GET.get('outcome',''); reason=request.GET.get('reason','')
    staff=request.GET.get('staff',''); code=request.GET.get('code','').strip(); start=request.GET.get('from',''); end=request.GET.get('to','')
    try: date.fromisoformat(start) if start else None
    except ValueError: start=''
    try: date.fromisoformat(end) if end else None
    except ValueError: end=''
    if staff.isdigit(): events=events.filter(actor_id=int(staff))
    events=filter_local_dates(events,'occurred_at',date.fromisoformat(start) if start else None,
                              date.fromisoformat(end) if end else None)
    if code: events=events.filter(card__code__icontains=code)
    expired_reason=Q(details__reason_code='EXPIRED_CARD')|Q(details__reason='This card has expired.')
    rejected_count=events.filter(outcome='REJECTED').count()
    expired_rejected_count=events.filter(action='REDEMPTION',outcome='REJECTED').filter(expired_reason).count()
    presentations=events.filter(action='REDEMPTION',outcome='REJECTED',details__stage='presentation',details__reason_code='EXPIRED_CARD')
    expired_presentation_count=presentations.count()
    expired_by_card=presentations.values('card__code','actor__username').annotate(total=Count('id')).order_by('-total','card__code','actor__username')[:20]
    if action in CARD_AUDIT_ACTIONS: events=events.filter(action=action)
    if outcome in ('SUCCESS','REJECTED'): events=events.filter(outcome=outcome)
    if reason=='expired': events=events.filter(expired_reason)
    return render(request,'giftcards/audit.html',{'events':events[:500],'actions':CARD_AUDIT_ACTIONS,'staff':User.objects.filter(profile__role='STAFF'),'action_filter':action,'outcome_filter':outcome,'reason_filter':reason,'staff_filter':staff,'code_filter':code,'from_filter':start,'to_filter':end,'rejected_count':rejected_count,'expired_rejected_count':expired_rejected_count,'expired_presentation_count':expired_presentation_count,'expired_by_card':expired_by_card})
@role_required('ADMIN')
def report_csv(request):
    import csv
    response=HttpResponse(content_type='text/csv'); response['Content-Disposition']='attachment; filename="umerrick-gift-card-report.csv"'
    writer=csv.writer(response); writer.writerow(['Code','Type','Status','Generated','Generated by','Activated','Activated by','Customer phone','activation purchase amount','Expires','Redeemed','Redeemed by','Total purchase at redemption','Gift card discount','Payable after discount'])
    for c in GiftCard.objects.select_related('created_by','activated_by','redeemed_by','redemption'):
        redemption=getattr(c,'redemption',None)
        phone=("'"+c.customer_phone) if c.customer_phone else ''
        writer.writerow([c.code,c.get_kind_display(),c.display_status,c.created_at,c.created_by.username,c.activated_at,c.activated_by.username if c.activated_by else '',phone,c.activation_purchase_amount if c.activation_purchase_amount is not None else '',c.expires_at,c.redeemed_at,c.redeemed_by.username if c.redeemed_by else '',redemption.purchase_amount if redemption else '',redemption.discount_amount if redemption else '',redemption.payable_amount if redemption else ''])
    return response
