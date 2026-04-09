release: npm ci && npm run build:css && ls static/css && python manage.py collectstatic --noinput && python manage.py migrate --noinput
web: daphne -b 0.0.0.0 -p $PORT FEMS.asgi:application