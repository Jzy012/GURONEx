release: npm ci && npm run build:css && python manage.py migrate --noinput && python manage.py collectstatic --noinput
web: daphne -b 0.0.0.0 -p $PORT FEMS.asgi:application