#!/bin/bash
set -e

# Ждём, пока поднимется Postgres (важно на первом старте docker compose,
# когда контейнер web стартует быстрее контейнера db).
if [ -n "$POSTGRES_HOST" ]; then
  echo "Ждём Postgres на $POSTGRES_HOST:${POSTGRES_PORT:-5432}..."
  until nc -z "$POSTGRES_HOST" "${POSTGRES_PORT:-5432}"; do
    sleep 1
  done
  echo "Postgres доступен."
fi

# Миграции и статику гоняем только у web-контейнера (командой gunicorn),
# у worker/beat это же CMD не используется — см. docker-compose.prod.yml.
if [ "$1" = "gunicorn" ]; then
  echo "Применяем миграции..."
  python manage.py migrate --noinput

  echo "Собираем статику..."
  python manage.py collectstatic --noinput
fi

exec "$@"
