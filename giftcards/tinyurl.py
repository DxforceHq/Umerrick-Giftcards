"""Create short links for owner-initiated gift-card reminders."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class TinyURLUnavailable(Exception):
    pass


def shorten_card_url(destination):
    key = os.environ.get('TINYURL_API_KEY', '').strip()
    api_url = os.environ.get('TINYURL_API_URL', 'https://api.tinyurl.com').rstrip('/')
    parsed_api = urlparse(api_url)
    if not key or parsed_api.scheme != 'https' or parsed_api.hostname != 'api.tinyurl.com':
        raise TinyURLUnavailable('TinyURL is not configured')
    parsed_destination = urlparse(destination)
    if parsed_destination.scheme != 'https' or not parsed_destination.netloc:
        raise TinyURLUnavailable('Only public HTTPS card links can be shortened')

    request = Request(
        api_url + '/create',
        data=json.dumps({'url': destination, 'domain': 'tinyurl.com'}).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {key}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=5) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        raise TinyURLUnavailable('TinyURL request failed') from exc

    data = result.get('data') if isinstance(result, dict) else None
    short_url = data.get('tiny_url') if isinstance(data, dict) else None
    if not isinstance(short_url, str):
        raise TinyURLUnavailable('TinyURL returned no link')
    parsed = urlparse(short_url)
    if parsed.scheme != 'https' or parsed.hostname != 'tinyurl.com' or len(short_url) > 255 or len(short_url) >= len(destination):
        raise TinyURLUnavailable('TinyURL returned an invalid link')
    return short_url
