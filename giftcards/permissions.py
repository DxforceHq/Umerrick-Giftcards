from functools import wraps
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from .models import Profile, GiftCard, AuditEvent

def staff_can(user, permission):
    if user.is_superuser or getattr(getattr(user, 'profile', None), 'role', None) == Profile.Role.ADMIN:
        return True
    return bool(getattr(getattr(user, 'profile', None), permission, False))

def role_required(*roles, permission=None, any_permission=None):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            if not request.user.is_active: return HttpResponseForbidden()
            try: role=request.user.profile.role
            except Profile.DoesNotExist: role='ADMIN' if request.user.is_superuser else 'STAFF'
            allowed=(role in roles or request.user.is_superuser)
            if permission: allowed=allowed and staff_can(request.user,permission)
            if any_permission: allowed=allowed and any(staff_can(request.user, item) for item in any_permission)
            if not allowed:
                route=request.resolver_match.url_name
                if request.method == 'GET' and route in (
                    'generate', 'cards', 'card_detail', 'card_print', 'batch_print',
                    'staff', 'audit', 'prices', 'scanner',
                ):
                    from django.shortcuts import redirect
                    return redirect('dashboard')
                if route in ('activate','redeem'):
                    card=GiftCard.objects.filter(pk=kwargs.get('card_id')).first()
                    AuditEvent.objects.create(card=card,actor=request.user,action='ACTIVATION' if route=='activate' else 'REDEMPTION',previous_state=card.status if card else '',new_state=card.status if card else '',outcome='REJECTED',details={'reason':'permission denied'})
                return HttpResponseForbidden('You do not have permission to access this page.')
            if getattr(getattr(request.user,'profile',None),'must_change_password',False) and request.resolver_match.url_name not in ('password_change','logout'):
                from django.shortcuts import redirect
                return redirect('password_change')
            return view(request,*args,**kwargs)
        return wrapped
    return decorator
