import json

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def manifest(request):
    response = FileResponse(
        (settings.BASE_DIR / 'static' / 'manifest.json').open('rb'),
        content_type='application/manifest+json',
    )
    response['Cache-Control'] = 'public, max-age=300'
    return response


@require_GET
def icon(request, size):
    if size not in (180, 192, 512):
        raise Http404
    response = FileResponse(
        (settings.BASE_DIR / 'static' / 'brand' / f'pwa-symbol-{size}.png').open('rb'),
        content_type='image/png',
    )
    response['Cache-Control'] = 'public, max-age=86400'
    return response


@require_GET
def prices_worker(request):
    asset_paths = (
        'css/app.css', 'css/retail-workspace.css', 'js/app-shell.js',
        'js/camera-permission.js', 'js/password-visibility.js', 'js/prices.js',
        'brand/umerrick-logo-cutout.png',
    )
    assets = [staticfiles_storage.url(path) for path in asset_paths]
    script = (settings.BASE_DIR / 'static' / 'js' / 'prices-worker.js').read_text(encoding='utf-8')
    response = HttpResponse(script.replace('__PRICE_STATIC_ASSETS__', json.dumps(assets)), content_type='text/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response
