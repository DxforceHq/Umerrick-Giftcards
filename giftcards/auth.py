from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


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
