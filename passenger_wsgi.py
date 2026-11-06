"""Passenger entry point for the U_MERRICK production application.

Passenger imports this module before serving requests.  Load the production
environment first, then import Django so the production settings see the
values from .env.production.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

production_env = PROJECT_ROOT / ".env.production"
if not production_env.is_file():
    raise RuntimeError(
        f"Passenger production environment file is missing: {production_env}"
    )

load_dotenv(production_env, override=False)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "umerrick.settings.production")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
