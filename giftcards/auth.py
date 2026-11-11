from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.forms import AuthenticationForm
from math import ceil
from django.contrib.auth.views import LoginView
from django.shortcuts import render
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from urllib.parse import urlsplit


class CaseInsensitiveModelBackend(ModelBackend):
    """Authenticate the stored username regardless of the entered letter case."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        user_model = get_user_model()
        if username is None:
            username = kwargs.get(user_model.USERNAME_FIELD)
        if username is None or password is None:
            return None

        try:
            user = user_model._default_manager.get(
                **{f"{user_model.USERNAME_FIELD}__iexact": username}
            )
        except (user_model.DoesNotExist, user_model.MultipleObjectsReturned):
            # Match Django's timing protection for an unknown username.
            user_model().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    async def aauthenticate(self, request, username=None, password=None, **kwargs):
        user_model = get_user_model()
        if username is None:
            username = kwargs.get(user_model.USERNAME_FIELD)
        if username is None or password is None:
            return None

        try:
            user = await user_model._default_manager.aget(
                **{f"{user_model.USERNAME_FIELD}__iexact": username}
            )
        except (user_model.DoesNotExist, user_model.MultipleObjectsReturned):
            user_model().set_password(password)
            return None

        if await user.acheck_password(password) and self.user_can_authenticate(user):
            return user
        return None


def normalized_axes_username(request, credentials):
    """Count username case variants as one identity for login rate limiting."""
    field = settings.AXES_USERNAME_FORM_FIELD
    username = (credentials or {}).get(field)
    if username is None:
        request_data = getattr(request, "data", request.POST)
        username = request_data.get(field)
    return username.casefold() if isinstance(username, str) else username


class StaffAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': 'Incorrect username or password.',
    }


class PermissionAwareLoginView(LoginView):
    """Keep saved destinations from sending staff to admin or disabled features."""

    authentication_form = StaffAuthenticationForm

    def form_invalid(self, form):
        from axes.handlers.proxy import AxesProxyHandler

        username = self.request.POST.get(settings.AXES_USERNAME_FORM_FIELD, '')
        failures = AxesProxyHandler.get_failures(
            self.request, {settings.AXES_USERNAME_FORM_FIELD: username}
        ) if username else 0
        self.extra_context = {'contact_admin_hint': 5 <= failures < settings.AXES_FAILURE_LIMIT}
        return super().form_invalid(form)

    def get_success_url(self):
        destination = super().get_success_url()
        user = self.request.user
        from .models import Profile
        from .permissions import staff_can

        if user.is_superuser or getattr(getattr(user, 'profile', None), 'role', None) == Profile.Role.ADMIN:
            return destination
        try:
            route = resolve(urlsplit(destination).path).url_name
        except Resolver404:
            return reverse('dashboard')
        if route in ('dashboard', 'password_change'):
            return destination
        if route == 'prices' and staff_can(user, 'can_view_prices'):
            return destination
        if route == 'scanner' and (staff_can(user, 'can_activate_cards') or staff_can(user, 'can_redeem_cards')):
            return destination
        return reverse('dashboard')


def login_lockout_response(request, original_response=None, credentials=None):
    """Show the actual remaining lockout time after Axes reaches its limit."""
    from axes.helpers import get_client_ip_address, get_client_username, get_cool_off
    from axes.models import AccessAttempt

    username = get_client_username(request, credentials)
    attempt = AccessAttempt.objects.filter(
        username=username, ip_address=get_client_ip_address(request)
    ).order_by('-attempt_time').first()
    cooloff = get_cool_off(request)
    remaining = (attempt.attempt_time + cooloff - timezone.now()).total_seconds() if attempt else cooloff.total_seconds()
    seconds = max(1, ceil(remaining))
    response = render(request, 'registration/locked_out.html', {
        'retry_after_seconds': seconds,
    }, status=429)
    response['Retry-After'] = str(seconds)
    response['Cache-Control'] = 'no-store'
    return response
