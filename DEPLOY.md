# Деплой на сервер (Docker)

## Что изменилось/добавилось
- `Dockerfile` — теперь запускает `gunicorn` (не `runserver`), от непривилегированного пользователя.
- `docker-entrypoint.sh` — ждёт Postgres, накатывает миграции, собирает статику.
- `docker-compose.prod.yml` — прод-стек: `db`, `redis`, `web` (gunicorn), `worker` и `beat` (celery), `nginx`.
- `nginx/nginx.conf` — отдаёт `/static/` и `/media/` напрямую, остальное проксирует в gunicorn.
- `config/settings.py` — добавлены `STATIC_ROOT`, HTTPS/HSTS-настройки (включаются при `DEBUG=False`), `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`.
- `.dockerignore`, `.gitignore` — их не было вообще.

`docker-compose.yml` (без `.prod`) не трогал — это ваш локальный dev-стек (runserver, порты БД наружу).

## Шаги на сервере

1. Установите Docker и Docker Compose plugin (`docker compose version` должен работать).

2. Склонируйте репозиторий на сервер, зайдите в папку проекта.

3. Создайте `.env` на основе `.env.example` и заполните боевыми значениями:
   ```bash
   cp .env.example .env
   ```
   Обязательно поменяйте:
   - `DJANGO_SECRET_KEY` — сгенерируйте случайный (не оставляйте dev-значение).
   - `DJANGO_DEBUG=False`
   - `DJANGO_ALLOWED_HOSTS=shotforjob.ru,www.shotforjob.ru` (ваш домен/IP)
   - `CSRF_TRUSTED_ORIGINS=https://shotforjob.ru,https://www.shotforjob.ru`
   - `CORS_ALLOW_ALL_ORIGINS=False` и `CORS_ALLOWED_ORIGINS=https://shotforjob.ru` (если фронт на другом домене)
   - `POSTGRES_PASSWORD` — надёжный пароль
   - ключи Polza.ai, Yandex S3, SMTP, Robokassa — боевые, не тестовые

4. В `nginx/nginx.conf` замените `server_name _;` на ваш домен.

5. Соберите и поднимите:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```
   Entrypoint сам применит миграции и соберёт статику при старте `web`.

6. Создайте суперпользователя для админки:
   ```bash
   docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
   ```

7. Проверьте логи, если что-то не так:
   ```bash
   docker compose -f docker-compose.prod.yml logs -f web worker beat
   ```

## HTTPS
Сейчас nginx слушает только 80 порт (http). Проще всего добавить https через certbot:

```bash
docker compose -f docker-compose.prod.yml run --rm -p 80:80 \
  -v ./certbot/conf:/etc/letsencrypt certbot/certbot certonly \
  --standalone -d shotforjob.ru -d www.shotforjob.ru
```

Затем в `nginx/nginx.conf` раскомментируйте `listen 443 ssl;` блок с путями к сертификатам, в `docker-compose.prod.yml` — порт `443` и volume `./certbot/conf`, и настройте автопродление сертификата (cron/systemd timer с `certbot renew`).

## Обновление проекта (деплой новой версии)
```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```
Миграции и collectstatic снова применятся автоматически через entrypoint.
