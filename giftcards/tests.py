import threading, uuid
from decimal import Decimal
from datetime import datetime, time, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo
from django.conf import settings
from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, skipUnlessDBFeature, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import AuditEvent, GiftCard, Redemption, Profile, PriceItem

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PriceListTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_superuser('priceadmin',password='Strong-admin-pass-912!')
        self.staff=User.objects.create_user('pricestaff',password='Strong-staff-pass-912!')
        self.staff.profile.must_change_password=False
        self.staff.profile.save(update_fields=['must_change_password'])

    def test_admin_maintains_prices_and_staff_only_sees_active(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('price_create'),{'name':'  Classic  Shirt  ','price':'12500.50'})
        item=PriceItem.objects.get()
        self.assertEqual(item.name,'Classic Shirt')
        self.assertEqual(str(item.price),'12500.50')
        self.client.post(reverse('price_create'),{'name':'CLASSIC SHIRT','price':'1.00'})
        self.assertEqual(PriceItem.objects.count(),1)
        self.client.post(reverse('price_update',args=[item.pk]),{'name':'Classic Shirt','price':'13000.00'})
        item.refresh_from_db()
        self.assertEqual(str(item.price),'13000.00')
        self.assertEqual(item.updated_by,self.admin)
        price_changed_at=item.price_updated_at
        self.assertEqual(len(self.client.get(reverse('prices_data')).json()['items']),1)
        self.client.post(reverse('price_toggle',args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.price_updated_at,price_changed_at)
        self.assertEqual(self.client.get(reverse('prices_data')).json()['items'],[])
        self.assertContains(self.client.get(reverse('prices')),'Restore item')
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get(reverse('prices')),'Classic Shirt')
        self.assertEqual(self.client.post(reverse('price_update',args=[item.pk]),{'name':'Changed','price':'1'}).status_code,403)
        self.assertEqual(self.client.post(reverse('price_toggle',args=[item.pk])).status_code,403)
        self.assertEqual(self.client.post(reverse('price_create'),{'name':'Other','price':'1'}).status_code,403)
        item.refresh_from_db()
        self.assertEqual(item.name,'Classic Shirt')
        self.client.force_login(self.admin)
        self.client.post(reverse('price_toggle',args=[item.pk]))
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('prices_data')).json()['items'][0]['price'],'13000.00')

    def test_invalid_price_and_unauthenticated_access(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('price_create'),{'name':'Invalid','price':'-1'})
        self.assertFalse(PriceItem.objects.exists())
        self.client.logout()
        self.assertEqual(self.client.get(reverse('prices_data')).status_code,302)
        response=self.client.get(reverse('prices_worker'))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Service-Worker-Allowed'],'/')
        self.assertIn(b'/static/js/prices.js',response.content)
        self.assertNotIn(b'__PRICE_STATIC_ASSETS__',response.content)

    def test_bulk_add_saves_valid_items_and_skips_duplicates(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('price_create'),{
            'name':['  silk   shirt  ','DENIM JACKET','linen trousers'],
            'price':['12000.00','25000.50','18000.00'],
        })
        self.assertEqual(list(PriceItem.objects.values_list('name',flat=True)),
                         ['Denim Jacket','Linen Trousers','Silk Shirt'])
        response=self.client.post(reverse('price_create'),{
            'name':['new cap','DENIM JACKET'], 'price':['5000','9000'],
        },follow=True)
        self.assertTrue(PriceItem.objects.filter(name='New Cap').exists())
        self.assertContains(response,'1 item added to the price list.')
        self.assertContains(response,'1 duplicate item skipped: Denim Jacket.')
        self.client.post(reverse('price_create'),{
            'name':['belt','BELT'], 'price':['1000','1100'],
        })
        self.assertEqual(PriceItem.objects.filter(name='Belt').count(),1)
        self.assertEqual(str(PriceItem.objects.get(name='Belt').price),'1000.00')
        self.client.post(reverse('price_create'),{
            'name':['Canvas Bag','Broken Price'], 'price':['8500','-1'],
        })
        self.assertTrue(PriceItem.objects.filter(name='Canvas Bag').exists())
        self.assertFalse(PriceItem.objects.filter(name='Broken Price').exists())
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('price_create'),{
            'name':['forbidden','another'], 'price':['1','2'],
        }).status_code,403)
        self.assertEqual(PriceItem.objects.count(),6)

    def test_large_bulk_add_keeps_other_items_when_a_name_repeats(self):
        self.client.force_login(self.admin)
        names=[f'Item {number}' for number in range(41)]
        names.insert(25,'item 5')
        response=self.client.post(reverse('price_create'),{
            'name':names,'price':['1000']*len(names),
        },follow=True)
        self.assertEqual(PriceItem.objects.count(),41)
        self.assertContains(response,'41 items added to the price list.')
        self.assertContains(response,'1 duplicate item skipped: Item 5.')

    def test_app_shell_has_refresh_and_signed_in_welcome(self):
        self.client.force_login(self.staff)
        response=self.client.get(reverse('dashboard'))
        self.assertContains(response,'class="app-refresh"')
        self.assertContains(response,'id="app-welcome"')
        self.assertContains(response,'Hello, pricestaff')
        self.client.logout()
        response=self.client.get(reverse('login'))
        self.assertNotContains(response,'id="app-welcome"')

    def test_admin_price_rows_are_inline_editable(self):
        PriceItem.objects.create(name='Test Shirt',price='4500.00',updated_by=self.admin)
        PriceItem.objects.create(name='Old Shirt',price='3200.00',is_active=False,updated_by=self.admin)
        self.client.force_login(self.admin)
        response=self.client.get(reverse('prices'))
        self.assertContains(response,'class="price-row price-admin-item"')
        self.assertContains(response,'class="price-admin-summary"')
        self.assertContains(response,'class="price-inline-editor"')
        self.assertContains(response,'Save price')
        self.assertContains(response,'Make inactive')
        self.assertContains(response,'Inactive')
        self.assertNotContains(response,'Manage items')
        self.client.force_login(self.staff)
        response=self.client.get(reverse('prices'))
        self.assertNotContains(response,'price-admin-item')
from .services import generate_cards, card_discount, activate, redeem
from .views import qr_payload

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LoginFlowTests(TestCase):
    def setUp(self):
        self.staff=User.objects.create_user('login_staff',password='Strong-staff-pass-912!')
        self.staff.profile.must_change_password=False
        self.staff.profile.can_view_prices=False
        self.staff.profile.save(update_fields=['must_change_password','can_view_prices'])

    def test_saved_admin_and_unpermitted_destinations_open_staff_dashboard(self):
        for destination in ('/staff/','/prices/'):
            self.client.logout()
            response=self.client.post(reverse('login')+'?next='+destination,{
                'username':'LOGIN_STAFF','password':'Strong-staff-pass-912!'
            })
            self.assertRedirects(response,reverse('dashboard'),fetch_redirect_response=False)
        self.staff.profile.can_view_prices=True
        self.staff.profile.save(update_fields=['can_view_prices'])
        self.client.logout()
        response=self.client.post(reverse('login')+'?next=/prices/',{
            'username':'login_staff','password':'Strong-staff-pass-912!'
        })
        self.assertRedirects(response,reverse('prices'),fetch_redirect_response=False)

    def test_five_failures_show_reset_help_and_ten_lock_for_five_minutes(self):
        url=reverse('login')
        for attempt in range(1,11):
            response=self.client.post(url,{'username':'LoGiN_StAfF','password':'incorrect'})
            if attempt==1:
                self.assertContains(response,'Incorrect username or password.')
                self.assertNotContains(response,'case-sensitive')
            if attempt==5:
                self.assertContains(response,'Ask an admin to reset it.')
                self.assertEqual(response.content.decode().count('Ask an admin to reset it.'),1)
            if attempt==10:
                self.assertEqual(response.status_code,429)
                self.assertContains(response,'five minutes',status_code=429)
                self.assertContains(response,'login-retry-countdown',status_code=429)
                self.assertLessEqual(int(response['Retry-After']),300)
        self.assertEqual(settings.AXES_FAILURE_LIMIT,10)
        self.assertEqual(settings.AXES_COOLOFF_TIME,timedelta(minutes=5))
        from axes.models import AccessAttempt
        AccessAttempt.objects.update(attempt_time=timezone.now()-timedelta(minutes=5,seconds=1))
        response=self.client.post(url,{'username':'login_staff','password':'Strong-staff-pass-912!'})
        self.assertRedirects(response,reverse('dashboard'),fetch_redirect_response=False)

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class GiftCardTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_superuser('admin',password='Strong-admin-pass-912!')
        self.staff=User.objects.create_user('staff',password='Strong-staff-pass-912!')
        self.staff.profile.must_change_password=False; self.staff.profile.save(update_fields=['must_change_password'])
    def card(self,kind='N10',status='GENERATED',hours=80,expiry_days=60):
        now=timezone.now(); c=GiftCard.objects.create(code='-'.join([uuid.uuid4().hex[i:i+4].upper() for i in range(0,16,4)]),kind=kind,status=status,created_by=self.admin)
        if status in ('ACTIVE','REDEEMED'):
            c.activated_at=now-timedelta(hours=hours); c.expires_at=now+timedelta(days=expiry_days); c.activated_by=self.staff
            if status=='REDEEMED': c.redeemed_at=now; c.redeemed_by=self.staff
            c.save()
        return c
    def test_admin_generates_one_and_bulk_unique_codes(self):
        one=generate_cards(self.admin,'N10',1); bulk=generate_cards(self.admin,'N15',12)
        self.assertEqual(len(one),1); self.assertEqual(len(bulk),12)
        self.assertEqual(len(set(GiftCard.objects.values_list('code',flat=True))),13)
        self.assertTrue(all(c.status=='GENERATED' and c.created_by==self.admin for c in bulk))
    def test_qr_identifies_card_and_is_png(self):
        c=generate_cards(self.admin,'PCT10',1)[0]; self.client.force_login(self.admin)
        r=self.client.get(reverse('card_qr',args=[c.id])); self.assertEqual(r['Content-Type'],'image/png'); self.assertTrue(r.content.startswith(b'\x89PNG'))
    def test_server_verifies_signed_qr_and_rejects_tampering(self):
        card=self.card(); other=self.card(); self.client.force_login(self.staff)
        payload=qr_payload(RequestFactory().get('/scan/'),card)
        response=self.client.post(reverse('card_lookup'),data={'qr':payload},content_type='application/json')
        self.assertEqual(response.status_code,200); self.assertEqual(response.json()['id'],str(card.id))
        legacy=self.client.post(reverse('card_lookup'),data={'qr':f'/scan/?card={card.id}'},content_type='application/json')
        self.assertEqual(legacy.status_code,200); self.assertEqual(legacy.json()['id'],str(card.id))
        for invalid in (payload.replace(str(card.id),str(other.id)),str(card.id)):
            response=self.client.post(reverse('card_lookup'),data={'qr':invalid},content_type='application/json')
            self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get(reverse('card_lookup'),{'card':str(card.id)}).status_code,405)
        self.assertFalse(AuditEvent.objects.filter(action='CARD_LOOKUP').exists())
    def test_admin_generation_endpoint_and_staff_denial(self):
        self.client.force_login(self.admin); r=self.client.post(reverse('generate'),{'kind':'N10','count':1}); self.assertEqual(r.status_code,200); self.assertEqual(GiftCard.objects.count(),1)
        self.client.force_login(self.staff); self.assertRedirects(self.client.get(reverse('generate')),reverse('dashboard'),fetch_redirect_response=False)
    def test_staff_activates_card_and_records_times(self):
        c=self.card(); self.client.force_login(self.staff); r=self.client.post(reverse('activate',args=[c.id]),content_type='application/json',data='{"customer_phone":"+2347012345678"}')
        c.refresh_from_db(); self.assertEqual(r.status_code,200); self.assertEqual(c.status,'ACTIVE'); self.assertEqual(c.activated_by,self.staff); self.assertAlmostEqual((c.expires_at-c.activated_at).total_seconds(),60*86400,delta=1)
        event=AuditEvent.objects.filter(card=c,action='ACTIVATION').get(); self.assertEqual(event.outcome,'SUCCESS')
    def test_unauthenticated_cannot_activate(self):
        c=self.card(); self.assertEqual(self.client.post(reverse('activate',args=[c.id])).status_code,302); c.refresh_from_db(); self.assertEqual(c.status,'GENERATED')
    def test_duplicate_activation_rejected_and_audited(self):
        c=self.card('N10','ACTIVE'); self.client.force_login(self.staff); r=self.client.post(reverse('activate',args=[c.id]),content_type='application/json',data='{}')
        self.assertEqual(r.status_code,409); self.assertTrue(AuditEvent.objects.filter(card=c,action='ACTIVATION',outcome='REJECTED').exists())
    def test_waiting_period_boundary_exact(self):
        c=self.card('N10','ACTIVE',hours=72); now=timezone.now(); self.assertEqual(c.display_status,'READY')
        with patch('giftcards.services.database_now',return_value=c.activated_at+timedelta(hours=72)-timedelta(microseconds=1)):
            with self.assertRaises(ValueError): redeem(c.id,self.staff,'50000')
        with patch('giftcards.services.database_now',return_value=c.activated_at+timedelta(hours=72)):
            rec=redeem(c.id,self.staff,'50000')
        self.assertEqual(rec.discount_amount,Decimal('10000.00'))
    def test_expiry_is_exclusive_at_and_after_boundary(self):
        c=self.card('N10','ACTIVE'); boundary=c.expires_at
        with patch('giftcards.services.database_now',return_value=boundary):
            with self.assertRaisesRegex(ValueError,'expired'): redeem(c.id,self.staff,'50000')
        c.refresh_from_db(); self.assertEqual(c.status,'ACTIVE'); self.assertTrue(AuditEvent.objects.filter(card=c,outcome='REJECTED').exists())
    def test_redeemed_card_is_single_use(self):
        c=self.card('N10','ACTIVE'); first=redeem(c.id,self.staff,'50000'); self.assertEqual(first.payable_amount,Decimal('40000.00'))
        with self.assertRaises(ValueError): redeem(c.id,self.staff,'50000')
        c.refresh_from_db(); self.assertEqual(c.status,'REDEEMED'); self.assertEqual(Redemption.objects.filter(card=c).count(),1)
        self.assertEqual(AuditEvent.objects.filter(card=c,action='REDEMPTION',outcome='SUCCESS').count(),1)
    def test_fixed_and_percent_discounts(self):
        for kind,expected in [('N10','10000.00'),('N15','15000.00'),('PCT10','5000.00')]:
            c=self.card(kind); p,d,pay=card_discount(c,'50000.00'); self.assertEqual(d,Decimal(expected)); self.assertEqual(p-d,pay)
    def test_fixed_value_below_purchase_forfeits_balance(self):
        c=self.card('N10','ACTIVE'); p,d,pay=card_discount(c,'7000.00'); self.assertEqual((d,pay),(Decimal('7000.00'),Decimal('0.00')))
        rec=redeem(c.id,self.staff,'7000.00'); self.assertEqual(rec.discount_amount,Decimal('7000.00'))
    def test_failed_attempt_leaves_card_active_and_audited(self):
        c=self.card('N10','ACTIVE',hours=12)
        with self.assertRaises(ValueError): redeem(c.id,self.staff,'50000')
        c.refresh_from_db(); self.assertEqual(c.status,'ACTIVE'); self.assertTrue(AuditEvent.objects.filter(card=c,action='REDEMPTION',outcome='REJECTED').exists())
    def test_card_value_cannot_be_supplied_by_browser(self):
        c=self.card('N10','ACTIVE'); self.client.force_login(self.staff)
        r=self.client.post(reverse('preview',args=[c.id]),data='{"amount":"50000","value":"1","discount":"0"}',content_type='application/json')
        self.assertEqual(r.status_code,200); self.assertEqual(r.json()['discount_amount'],'10000.00')
    def test_staff_must_authenticate_to_change_password_and_password_is_hashed(self):
        r=self.client.get(reverse('password_change')); self.assertEqual(r.status_code,302)
        self.client.force_login(self.staff); self.assertNotEqual(self.staff.password,'Strong-staff-pass-912!'); self.assertTrue(self.staff.check_password('Strong-staff-pass-912!'))
    def test_staff_can_change_authenticated_password(self):
        self.client.force_login(self.staff); r=self.client.post(reverse('password_change'),{'old_password':'Strong-staff-pass-912!','new_password1':'New-very-strong-pass-783!','new_password2':'New-very-strong-pass-783!'})
        self.staff.refresh_from_db(); self.assertEqual(r.status_code,302); self.assertTrue(self.staff.check_password('New-very-strong-pass-783!')); self.assertFalse(self.staff.profile.must_change_password)
        self.assertFalse(AuditEvent.objects.filter(action='PASSWORD_CHANGED').exists())
    def test_staff_create_is_admin_only(self):
        self.client.force_login(self.staff); self.assertRedirects(self.client.get(reverse('staff')),reverse('dashboard'),fetch_redirect_response=False)
        self.client.force_login(self.admin); r=self.client.post(reverse('staff'),{'username':'newstaff','password':'New-strong-password-492!'}); self.assertEqual(r.status_code,302)
        new=User.objects.get(username='newstaff'); self.assertTrue(new.profile.must_change_password); self.assertFalse(AuditEvent.objects.filter(action='STAFF_CREATED').exists())
    def test_deactivated_staff_cannot_keep_session(self):
        self.client.force_login(self.staff); self.staff.is_active=False; self.staff.save(update_fields=['is_active'])
        self.assertNotEqual(self.client.get(reverse('scanner')).status_code,200)
    def test_manual_code_lookup_fallback(self):
        c=self.card(); self.client.force_login(self.staff); r=self.client.post(reverse('card_lookup'),data='{' + '"code":"' + c.code + '"}',content_type='application/json')
        self.assertEqual(r.status_code,200); self.assertEqual(r.json()['id'],str(c.id))
    def test_qr_and_manual_lookup_reject_unknown_code(self):
        self.client.force_login(self.staff); r=self.client.post(reverse('card_lookup'),data='{"code":"ZZZZ-ZZZZ-ZZZZ-ZZZZ"}',content_type='application/json'); self.assertEqual(r.status_code,404)
    def test_redemption_unique_database_constraint(self):
        c=self.card('N10','ACTIVE'); redeem(c.id,self.staff,'50000')
        with self.assertRaises(IntegrityError):
            with transaction.atomic(): Redemption.objects.create(card=c,staff=self.staff,purchase_amount=1,discount_amount=1,payable_amount=0)

    def test_admin_can_reset_staff_password_and_force_change(self):
        self.client.force_login(self.admin); new='Reset-strong-password-792!'
        response=self.client.post(reverse('staff_reset',args=[self.staff.id]),{'password':new})
        self.staff.refresh_from_db(); self.assertEqual(response.status_code,302); self.assertTrue(self.staff.check_password(new)); self.assertTrue(self.staff.profile.must_change_password)
        self.assertFalse(AuditEvent.objects.filter(action='PASSWORD_RESET').exists())
    def test_staff_admin_route_denial_is_not_card_audit(self):
        self.client.force_login(self.staff); self.assertRedirects(self.client.get(reverse('generate')),reverse('dashboard'),fetch_redirect_response=False)
        self.assertFalse(AuditEvent.objects.filter(action='ADMIN_ACCESS_DENIED').exists())

    def test_dashboard_and_scanner_templates_render(self):
        self.client.force_login(self.admin); self.assertEqual(self.client.get(reverse('dashboard')).status_code,200)
        self.client.force_login(self.staff); self.assertEqual(self.client.get(reverse('dashboard')).status_code,200)
        scanner_response=self.client.get(reverse('scanner'))
        self.assertEqual(scanner_response.status_code,200)
        self.assertContains(scanner_response,'vendor/jsQR.js')
        self.assertContains(scanner_response,'id="camera"')
        self.client.force_login(self.admin)
        for page in ('cards','staff','audit'): self.assertEqual(self.client.get(reverse(page)).status_code,200)
        self.assertEqual(self.client.get(reverse('report_csv')).status_code,200)
    def test_dashboard_chart_uses_each_operation_timestamp_in_selected_period(self):
        today=timezone.localdate()
        earlier=self.card('N10','ACTIVE',hours=1)
        earlier.created_at=timezone.now()-timedelta(days=10)
        earlier.activated_at=timezone.now()
        earlier.save(update_fields=['created_at','activated_at'])
        redeemed=self.card('N15','REDEEMED',hours=80)
        self.client.force_login(self.admin)
        response=self.client.get(reverse('dashboard'),{'period':'custom','from':today.isoformat(),'to':today.isoformat()})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['stats']['TOTAL'],1)
        self.assertEqual(response.context['chart']['issued'],[1])
        self.assertEqual(response.context['chart']['activated'],[1])
        self.assertEqual(response.context['chart']['redeemed'],[1])
        self.assertContains(response,'id="activity-chart-data"')
        self.assertContains(response,'js/dashboard-chart.js')
    def test_dashboard_invalid_custom_dates_fall_back_to_30_days(self):
        self.client.force_login(self.admin)
        response=self.client.get(reverse('dashboard'),{'period':'custom','from':'bad','to':'bad'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['period'],'30d')
        self.assertContains(response,'Enter a valid date range')
    def test_dashboard_preset_ignores_hidden_custom_date_fields(self):
        self.client.force_login(self.admin)
        response=self.client.get(reverse('dashboard'),{'period':'30d','from':'2000-01-01','to':'2000-01-02'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['period'],'30d')
        self.assertEqual(response.context['to_filter'],timezone.localdate().isoformat())
    def test_local_date_boundaries_are_inclusive_at_start_exclusive_at_next_midnight(self):
        day=timezone.localdate()
        zone=ZoneInfo(settings.TIME_ZONE)
        midnight=datetime.combine(day,time.min,tzinfo=zone).astimezone(datetime_timezone.utc)
        before=self.card(); at_start=self.card(); at_end=self.card()
        for card,instant in ((before,midnight-timedelta(microseconds=1)),
                             (at_start,midnight),(at_end,midnight+timedelta(days=1))):
            card.created_at=instant; card.save(update_fields=['created_at'])
        self.client.force_login(self.admin)
        response=self.client.get(reverse('dashboard'),{'period':'custom','from':day.isoformat(),'to':day.isoformat()})
        self.assertEqual(response.context['stats']['TOTAL'],1)
        self.assertEqual(response.context['chart']['issued'],[1])
        register=self.client.get(reverse('cards'),{'from':day.isoformat(),'to':day.isoformat()})
        self.assertEqual([card.pk for card in register.context['cards']],[at_start.pk])
    def test_default_dashboard_period_filters_from_local_midnight(self):
        today=timezone.localdate(); start=today-timedelta(days=29)
        zone=ZoneInfo(settings.TIME_ZONE)
        lower=datetime.combine(start,time.min,tzinfo=zone).astimezone(datetime_timezone.utc)
        old=self.card(); included=self.card()
        old.created_at=lower-timedelta(microseconds=1); old.save(update_fields=['created_at'])
        included.created_at=lower; included.save(update_fields=['created_at'])
        self.client.force_login(self.admin)
        response=self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['period'],'30d')
        self.assertEqual(response.context['stats']['TOTAL'],1)
        self.assertEqual(sum(response.context['chart']['issued']),1)
    def test_camera_permission_ui_is_only_on_authenticated_pages(self):
        self.client.force_login(self.staff)
        dashboard=self.client.get(reverse('dashboard'))
        self.assertContains(dashboard,'id="camera-access"')
        self.assertContains(dashboard,'js/camera-permission.js')
        self.client.logout()
        login=self.client.get(reverse('login'))
        self.assertNotContains(login,'id="camera-access"')
        self.assertNotContains(login,'js/camera-permission.js')
    def test_rejected_preview_does_not_create_an_audit_event(self):
        card=self.card('N10','ACTIVE',hours=12); self.client.force_login(self.staff)
        response=self.client.post(reverse('preview',args=[card.id]),data='{"amount":"50000"}',content_type='application/json')
        self.assertEqual(response.status_code,400); self.assertFalse(AuditEvent.objects.filter(card=card).exists())
    def test_generation_does_not_create_audit_events(self):
        generate_cards(self.admin,'PCT10',3)
        self.assertFalse(AuditEvent.objects.exists())
    def test_audit_page_shows_only_activation_and_redemption(self):
        card=self.card('N10','ACTIVE')
        AuditEvent.objects.create(actor=self.admin,action='LOGIN',outcome='SUCCESS')
        redeem(card.id,self.staff,'50000')
        self.client.force_login(self.admin)
        response=self.client.get(reverse('audit'))
        self.assertEqual(response.status_code,200)
        self.assertEqual([event.action for event in response.context['events']],['REDEMPTION'])
        self.assertEqual(response.context['actions'],('ACTIVATION','REDEMPTION'))
    def test_successful_redemption_is_in_audit(self):
        c=self.card('N15','ACTIVE'); redeem(c.id,self.staff,'50000'); event=AuditEvent.objects.get(card=c,action='REDEMPTION')
        self.assertEqual(event.previous_state,'READY'); self.assertEqual(event.new_state,'REDEEMED'); self.assertEqual(event.outcome,'SUCCESS')


    def test_staff_permissions_guard_pages_and_card_apis(self):
        card=self.card(); self.client.force_login(self.staff)
        profile=self.staff.profile
        profile.can_activate_cards=False; profile.can_redeem_cards=False; profile.can_view_prices=False
        profile.save(update_fields=['can_activate_cards','can_redeem_cards','can_view_prices'])
        self.assertRedirects(self.client.get(reverse('scanner')),reverse('dashboard'),fetch_redirect_response=False)
        self.assertEqual(self.client.post(reverse('card_lookup'),data={'code':card.code},content_type='application/json').status_code,403)
        self.assertEqual(self.client.post(reverse('activate',args=[card.id]),data={'customer_phone':'+2347012345678'},content_type='application/json').status_code,403)
        self.assertEqual(self.client.post(reverse('preview',args=[card.id]),data={'amount':'50000'},content_type='application/json').status_code,403)
        self.assertEqual(self.client.post(reverse('redeem',args=[card.id]),data={'amount':'50000'},content_type='application/json').status_code,403)
        self.assertRedirects(self.client.get(reverse('prices')),reverse('dashboard'),fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('prices_data')).status_code,403)
        card.refresh_from_db(); self.assertEqual(card.status,GiftCard.Status.GENERATED)

    def test_owner_assigns_and_changes_staff_permissions(self):
        self.client.force_login(self.admin)
        response=self.client.post(reverse('staff'),{'username':'limited','password':'New-strong-password-492!','can_activate_cards':'on'})
        self.assertEqual(response.status_code,302)
        user=User.objects.get(username='limited')
        self.assertTrue(user.profile.can_activate_cards)
        self.assertFalse(user.profile.can_redeem_cards)
        self.assertFalse(user.profile.can_view_prices)
        response=self.client.post(reverse('staff_permissions',args=[user.id]),{'can_redeem_cards':'on','can_view_prices':'on'})
        self.assertEqual(response.status_code,302)
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.can_activate_cards)
        self.assertTrue(user.profile.can_redeem_cards)
        self.assertTrue(user.profile.can_view_prices)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('staff_permissions',args=[user.id]),{}).status_code,403)

    def test_staff_with_one_card_permission_only_sees_its_action(self):
        profile=self.staff.profile
        profile.can_redeem_cards=False
        profile.save(update_fields=['can_redeem_cards'])
        generated=self.card()
        ready=self.card('N10','ACTIVE')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('scanner')).status_code,200)
        lookup=self.client.post(reverse('card_lookup'),data={'code':generated.code},content_type='application/json')
        self.assertTrue(lookup.json()['can_activate'])
        self.assertFalse(lookup.json()['can_redeem'])
        self.assertEqual(self.client.post(reverse('activate',args=[generated.id]),data={'customer_phone':'+2347012345678'},content_type='application/json').status_code,200)
        self.assertEqual(self.client.post(reverse('preview',args=[ready.id]),data={'amount':'50000'},content_type='application/json').status_code,403)
        self.assertEqual(self.client.post(reverse('redeem',args=[ready.id]),data={'amount':'50000'},content_type='application/json').status_code,403)
        ready.refresh_from_db(); self.assertEqual(ready.status,GiftCard.Status.ACTIVE)

    def test_performance_credits_activator_not_redeemer(self):
        other=User.objects.create_user('other_staff')
        self.card('N10','REDEEMED')
        self.card('N15','ACTIVE')
        card=self.card('N10','REDEEMED')
        card.redeemed_by=other; card.save(update_fields=['redeemed_by'])
        self.client.force_login(self.admin)
        response=self.client.get(reverse('dashboard'))
        person=next(person for person in response.context['staff_performance'] if person.pk==self.staff.pk)
        self.assertEqual((person.total_activated,person.total_redeemed,person.redemption_rate),(3,2,66.7))
        other_person=next(person for person in response.context['staff_performance'] if person.pk==other.pk)
        self.assertEqual((other_person.total_activated,other_person.total_redeemed,other_person.redemption_rate),(0,0,0))

    def test_performance_includes_admin_activations(self):
        redeemed=self.card('N10','REDEEMED')
        redeemed.activated_by=self.admin
        redeemed.redeemed_by=self.staff
        redeemed.save(update_fields=['activated_by','redeemed_by'])
        active=self.card('N15','ACTIVE')
        active.activated_by=self.admin
        active.save(update_fields=['activated_by'])
        self.client.force_login(self.admin)
        response=self.client.get(reverse('dashboard'))
        admin_row=next(person for person in response.context['staff_performance'] if person.pk==self.admin.pk)
        self.assertEqual((admin_row.total_activated,admin_row.total_redeemed,admin_row.redemption_rate),(2,1,50.0))
        self.assertContains(response,'Admin')
        self.assertContains(response,'id="staff-performance"')
        self.assertContains(response,'id="staff-performance-query"')

class ConcurrentRedemptionTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_two_redemptions_racing_only_allow_one_success(self):
        from django.db import close_old_connections
        staff=User.objects.create_user('race-staff'); creator=User.objects.create_user('race-admin')
        now=timezone.now(); card=GiftCard.objects.create(code='RACE-CODE-ABCD-EFGH',kind='N10',status='ACTIVE',created_by=creator,activated_by=staff,activated_at=now-timedelta(hours=80),expires_at=now+timedelta(days=57))
        barrier=threading.Barrier(2); outcomes=[]
        def worker():
            close_old_connections()
            try:
                actor=User.objects.get(pk=staff.pk); barrier.wait(timeout=10)
                redeem(card.pk,actor,'50000'); outcomes.append('success')
            except ValueError: outcomes.append('rejected')
            finally: close_old_connections()
        workers=[threading.Thread(target=worker) for _ in range(2)]
        for thread in workers: thread.start()
        for thread in workers: thread.join(timeout=15)
        self.assertTrue(all(not thread.is_alive() for thread in workers))
        self.assertCountEqual(outcomes,['success','rejected'])
        self.assertEqual(Redemption.objects.filter(card=card).count(),1)
