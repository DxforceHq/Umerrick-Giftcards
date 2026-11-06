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

The Namecheap Python application and Git checkout share one directory:
`/home/clocojzu/repo/umerrick`. Configure **Setup Python App** with this
application root, `passenger_wsgi.py` as the startup file, and `application`
as the entry point. Select Python 3.13 and verify the virtual environment path
shown by cPanel matches the one in `.cpanel.yml` (currently
`/home/clocojzu/virtualenv/repo/umerrick/3.13/bin/python`).

Create `/home/clocojzu/repo/umerrick/.env.production` on the server with
restrictive file permissions. It is ignored by Git. Do not place production
secrets in `.cpanel.yml` or in a public web directory. The Passenger entry
point loads this file before Django starts.

### Namecheap cPanel Git deployment

cPanel's Git Version Control feature looks for the hidden file `.cpanel.yml`
at the repository root. Because the checkout is already the Python application
root, the manifest does not copy source files. It installs dependencies in the
existing virtual environment, imports `passenger_wsgi.py` so the production
environment is loaded, runs `collectstatic`, and touches `tmp/restart.txt` to
reload Passenger. Confirm the two paths in `.cpanel.yml` match **Setup Python
App** before deploying. The dependency installation task supplies
`python-dotenv` for the following collectstatic task.

Use cPanel **Git Version Control → Update from Remote → Deploy HEAD Commit**
for future releases, then check the deployment output. This manifest does not
run database migrations. Review and apply new migrations separately using
cPanel's Python script facility and the production settings. Never reset the
production database as part of deployment.

After deployment, verify that `/static/css/app.css`,
`/static/css/retail-workspace.css`, and `/static/js/app-shell.js` return assets
on the production domain, then check the login and admin pages. WhiteNoise
serves the collected files from the checkout's `staticfiles` directory.

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
