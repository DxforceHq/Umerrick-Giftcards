from functools import wraps
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from .models import Profile, GiftCard, AuditEvent
def role_required(*roles):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            if not request.user.is_active: return HttpResponseForbidden()
            try: role=request.user.profile.role
            except Profile.DoesNotExist: role='ADMIN' if request.user.is_superuser else 'STAFF'
            if role not in roles and not request.user.is_superuser:
                route=request.resolver_match.url_name
                if route in ('activate','redeem'):
                    card=GiftCard.objects.filter(pk=kwargs.get('card_id')).first()
                    AuditEvent.objects.create(card=card,actor=request.user,action='ACTIVATION' if route=='activate' else 'REDEMPTION',previous_state=card.status if card else '',new_state=card.status if card else '',outcome='REJECTED',details={'reason':'unauthorized role'})
                return HttpResponseForbidden('You do not have permission to access this page.')
            if getattr(getattr(request.user,'profile',None),'must_change_password',False) and request.resolver_match.url_name not in ('password_change','logout'):
                from django.shortcuts import redirect
                return redirect('password_change')
            return view(request,*args,**kwargs)
        return wrapped
    return decorator
