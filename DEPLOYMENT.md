# U_MERRICK development and production workflow

The project has two explicit Django settings modules:

- umerrick.settings.development — local development and test work. It loads
  the ignored root .env file and uses SQLite when DATABASE_URL is absent.
- umerrick.settings.production — the live server. It never loads a local
  .env file, requires all security-sensitive environment variables, and
  accepts only a MySQL DATABASE_URL.

This prevents a production process from silently using the developer
configuration.

## Local development

From the U_MERRICK directory:

    Copy-Item .env.development.example .env
    # Edit .env and keep it out of Git.
    .\.dx\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    python manage.py migrate
    python manage.py runserver

manage.py defaults to umerrick.settings.development, so local commands
continue to use SQLite unless a development DATABASE_URL is supplied.

Run the local checks before committing:

    python manage.py check
    python manage.py test giftcards
    python manage.py makemigrations --check --dry-run

## GitHub workflow

Push only source code, migrations, templates, static assets, requirements,
documentation, and workflow files. Never push:

- .env
- production credentials
- db.sqlite3
- staticfiles/
- uploaded media
- private keys or database dumps

.github/workflows/ci.yml installs dependencies and runs Django checks and the
gift-card test suite for every push to main and every pull request. Merge only
when CI is green.

## Production server

Create the production environment in the server's secret manager or service
unit. Do not copy the developer .env file to the server.

Use .env.production.example as the variable checklist:

    DJANGO_SETTINGS_MODULE=umerrick.settings.production
    DJANGO_DEBUG=0
    DJANGO_SECRET_KEY=<new random secret, at least 50 characters>
    DJANGO_ALLOWED_HOSTS=app.example.com
    DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com
    DJANGO_HSTS_SECONDS=31536000
    DJANGO_SESSION_COOKIE_AGE=28800
    DATABASE_URL=mysql://umerrick_app:<url-encoded-password>@db-host:3306/umerrick

The database user used by Gunicorn should be a least-privilege runtime user.
Run migrations with a separate migration-capable account so the append-only
audit triggers can be created.

Install and deploy:

    python -m pip install -r requirements.txt
    python manage.py check --deploy
    python manage.py migrate
    python manage.py collectstatic --noinput
    gunicorn --bind 127.0.0.1:8000 umerrick.wsgi:application

The reverse proxy must terminate TLS, redirect HTTP to HTTPS, and pass:

    X-Forwarded-Proto: https

Only expose the reverse proxy publicly. Keep MySQL private.

## Passenger hosting

For cPanel or Passenger hosting:

1. Upload the project to the application root.
2. Create the production virtual environment and install
   requirements.txt into it.
3. Keep .env.production in the application root with restrictive file
   permissions; never place it in a public static directory.
4. Configure Passenger to use passenger_wsgi.py as the startup file.
5. Configure Passenger to use the production virtualenv interpreter.
6. Set the application root and restart Passenger after changes.

passenger_wsgi.py loads .env.production before importing Django, so the
Passenger process uses umerrick.settings.production rather than the local
development settings.

### Namecheap cPanel Git deployment

cPanel's Git Version Control feature looks for the hidden file `.cpanel.yml`
at the repository root. The checked-in manifest in this project:

- copies only application source, templates, and static source files;
- leaves `.env.production`, media, `staticfiles`, and SQLite data on the
  server untouched;
- installs `requirements.txt` into the cPanel Python application's virtual
  environment;
- runs `collectstatic`; and
- touches `tmp/restart.txt` so Passenger reloads the new code.

Before deploying, edit `.cpanel.yml` and replace `CPANEL_USER`, `APP_ROOT`,
and the Python version in `VENV_PYTHON` with the values shown by Namecheap's
**Setup Python App** page. Provision the real `.env.production` in the
application root (the Passenger entry point requires that file); cPanel
environment variables may supplement it but do not replace it. The manifest
deliberately does not run migrations; apply them manually after reviewing the
release:

    /home/CPANEL_USER/virtualenv/umerrick/3.13/bin/python \
      /home/CPANEL_USER/umerrick/manage.py migrate \
      --settings=umerrick.settings.production

After the first deploy, set the Python application's **Application root** to
`APP_ROOT`, **Application startup file** to `passenger_wsgi.py`, and restart
the application. Keep the repository's `.env.production` out of Git and do
not put it under `public_html`.

## Release checks

Before switching traffic to a release:

1. Run check --deploy with the production settings and real environment.
2. Confirm the MySQL driver is installed and the database is reachable.
3. Run migrations on staging first.
4. Run the gift-card tests against MySQL InnoDB, including the concurrent
   redemption test.
5. Verify the MySQL audit triggers with SHOW TRIGGERS.
6. Verify Admin and Staff authorization, CSRF protection, HTTPS, secure
   cookies, QR validation, activation, expiry, and single-use redemption.
7. Take an encrypted backup and perform a restore test.

## Rollback

Keep the previous application release available. If a deployment fails,
route traffic back to the previous release, restore the database only when
the migration is reversible and the recovery plan requires it, then
investigate from logs. Do not reset the production database or delete
migrations as a rollback strategy.
