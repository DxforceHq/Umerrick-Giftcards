import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env.production"))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "umerrick.settings.production"
)

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()