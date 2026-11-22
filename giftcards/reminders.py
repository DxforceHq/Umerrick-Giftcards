"""Manual WhatsApp reminder policy and message composition."""
import calendar
from datetime import timedelta
from urllib.parse import urlencode

from django.utils import timezone

from .models import CardReminder, GiftCard
from .card_links import public_status_url


STAGES = (CardReminder.Stage.FIRST, CardReminder.Stage.SECOND, CardReminder.Stage.FINAL)


def one_month_later(value):
    month = value.month + 1
    year = value.year + (month > 12)
    month = (month - 1) % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def reminder_due_at(card, stage):
    ready_at = card.eligible_at
    if not ready_at or not card.expires_at:
        return None
    return {
        CardReminder.Stage.FIRST: ready_at + timedelta(days=7),
        CardReminder.Stage.SECOND: one_month_later(ready_at),
        CardReminder.Stage.FINAL: card.expires_at - timedelta(days=7),
    }[stage]


def next_reminder(card, sent_stages, now=None):
    now = now or timezone.now()
    if card.is_test or card.status != GiftCard.Status.ACTIVE or not card.customer_phone or not card.eligible_at or not card.expires_at or now >= card.expires_at or now < card.eligible_at:
        return None, None
    for stage in STAGES:
        if stage not in sent_stages:
            due_at = reminder_due_at(card, stage)
            return stage, due_at if due_at and now >= due_at else None
    return None, None


def reminder_message(card, stage, request, now=None, status_url=None):
    now = now or timezone.now()
    days_left = max(0, (timezone.localtime(card.expires_at).date() - timezone.localtime(now).date()).days)
    intro = {
        CardReminder.Stage.FIRST: 'Your U_MERRICK gift card is ready to be redeemed.',
        CardReminder.Stage.SECOND: 'Your U_MERRICK gift card is still ready to redeem.',
        CardReminder.Stage.FINAL: f'Your U_MERRICK gift card expires in {days_left} day{"s" if days_left != 1 else ""}.',
    }[stage]
    status_url = status_url or card.reminder_short_url or public_status_url(request, card)
    test_notice = 'TEST CARD — NOT VALID FOR REDEMPTION\n' if card.is_test else ''
    return f'{test_notice}*Hello! 👋 {intro}*\n\n🚀🚀Check your gift card status: {status_url}'


def whatsapp_url(card, stage, request, now=None, status_url=None):
    phone = ''.join(character for character in card.customer_phone if character.isdigit())
    return f'https://wa.me/{phone}?{urlencode({"text": reminder_message(card, stage, request, now, status_url)})}'
