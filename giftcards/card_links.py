"""Signed links for printed cards and compact customer status links."""
import base64
import binascii
import hmac
import re
import uuid
from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils.crypto import salted_hmac


QR_SIGNING_SALT = 'umerrick.gift-card.qr'
SHORT_LINK_SALT = 'umerrick.gift-card.short-link'


def card_token(card):
    return signing.Signer(salt=QR_SIGNING_SALT).sign(str(card.id))


def _short_signature(payload, secret):
    digest = salted_hmac(SHORT_LINK_SALT, payload, secret=secret).digest()[:12]
    return base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')


def short_card_token(card):
    payload = base64.urlsafe_b64encode(card.id.bytes).decode('ascii').rstrip('=')
    return payload + _short_signature(payload, settings.SECRET_KEY)


def card_id_from_short_token(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{38}', token):
        return None
    payload, signature = token[:22], token[22:]
    if not any(hmac.compare_digest(signature, _short_signature(payload, secret))
               for secret in (settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS)):
        return None
    try:
        return uuid.UUID(bytes=base64.urlsafe_b64decode(payload + '=='))
    except (ValueError, TypeError, binascii.Error):
        return None


def public_status_url(request, card):
    return request.build_absolute_uri(reverse('short_card_status', args=[short_card_token(card)]))
