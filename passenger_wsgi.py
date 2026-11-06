import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env.production")

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "umerrick.settings.production"
)

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
