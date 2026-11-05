from django.contrib import admin
from .models import Profile, GiftCard, Redemption, AuditEvent
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display=('user','role','must_change_password'); list_filter=('role',); readonly_fields=('user','role','must_change_password')
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
@admin.register(GiftCard)
class GiftCardAdmin(admin.ModelAdmin):
    list_display=('code','kind','status','created_at','activated_at','activation_purchase_amount','expires_at'); search_fields=('code','customer_phone')
    readonly_fields=('id','code','kind','status','created_at','created_by','activated_at','activated_by','customer_phone','activation_purchase_amount','expires_at','redeemed_at','redeemed_by','batch_id')
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
@admin.register(Redemption)
class RedemptionAdmin(admin.ModelAdmin):
    list_display=('card','staff','purchase_amount','discount_amount','payable_amount','created_at')
    readonly_fields=[f.name for f in Redemption._meta.fields]
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
@admin.register(AuditEvent)
class AuditAdmin(admin.ModelAdmin):
    list_display=('occurred_at','action','actor','card','outcome'); list_filter=('action','outcome'); search_fields=('card__code','actor__username'); readonly_fields=[f.name for f in AuditEvent._meta.fields]
    def get_queryset(self,request): return super().get_queryset(request).filter(action__in=('ACTIVATION','REDEMPTION'))
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
