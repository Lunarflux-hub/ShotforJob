# PhotoStudio — бэкенд ИИ-сервиса генерации фото

Django + DRF + Celery/Redis + Polza.ai + Yandex Cloud Object Storage.

## Архитектура

```
Клиент (SPA) ──HTTP/JSON──▶ Django REST Framework
                                  │
                                  │ создаёт Order + UploadedPhoto,
                                  │ ставит задачу в очередь
                                  ▼
                              Celery task ──▶ Polza.ai API (генерация)
                                  │
                                  ▼
                     Yandex Object Storage (сохранение результата)
                                  │
                                  ▼
                        Order.status = done, результат доступен
                        клиенту через GET /api/orders/{id}/ (поллинг)
```

Заказ (`Order`) — центральная сущность. Пользователь может быть:
- анонимным — тогда заказ привязывается к `anon_id` из httponly-cookie;
- авторизованным (JWT) — тогда заказ привязывается к `user`.

Это даёт возможность попробовать сервис без регистрации (п.7 в ТЗ),
а зарегистрированным — видеть историю (`GET /api/orders/history/`).

## Модели

- **PhotoStyle** — стиль генерации («Для документов», «Деловое портфолио», «Креативное»),
  хранит `prompt_template`, который уходит в Polza.ai.
- **Order** — заявка на генерацию: статус `pending → processing → done/failed`.
- **UploadedPhoto** — 1–3 исходных фото пользователя, привязанные к заказу.
- **GeneratedResult** — результат генерации (может быть несколько на заказ — для «Попробовать снова»).

## API

| Метод | Путь                          | Описание                                   |
|-------|-------------------------------|---------------------------------------------|
| GET   | `/api/styles/`                 | Список активных стилей для лендинга        |
| POST  | `/api/orders/`                  | Создать заказ (multipart: style_id, photos) |
| GET   | `/api/orders/{id}/`             | Статус и результат (для поллинга с фронта) |
| POST  | `/api/orders/{id}/retry/`       | Повторить генерацию с теми же фото          |
| GET   | `/api/orders/history/`          | История заказов текущего пользователя       |
| POST  | `/api/auth/register/`           | Регистрация                                 |
| POST  | `/api/auth/login/`              | Логин, возвращает JWT access/refresh        |
| POST  | `/api/auth/refresh/`            | Обновление access-токена                    |

Пример создания заказа (фронт):

```bash
curl -X POST http://localhost:8000/api/orders/ \
  -F "style_id=2" \
  -F "photos=@photo1.jpg" \
  -F "photos=@photo2.jpg" \
  -c cookies.txt
```

Дальше фронт поллит `GET /api/orders/{id}/` каждые 2–3 секунды,
пока `status` не станет `done` или `failed`.

## Запуск локально (без Docker, для MVP на SQLite)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# в .env добавьте: USE_SQLITE=True

python manage.py makemigrations photos accounts
python manage.py migrate
python manage.py loaddata apps/photos/fixtures/initial_styles.json
python manage.py createsuperuser

# терминал 1
python manage.py runserver

# терминал 2 (нужен запущенный Redis)
celery -A config worker -l info
```

## Запуск через Docker Compose (Postgres + Redis + web + worker)

```bash
cp .env.example .env   # заполните POLZA_API_KEY и YC_S3_* реальными значениями
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py loaddata apps/photos/fixtures/initial_styles.json
docker compose exec web python manage.py createsuperuser
```

## На что обратить внимание перед продакшеном

1. **Image-to-image в Polza.ai.** В ТЗ был указан эндпоинт
   `POST /v2/images/generations`, который в OpenAI-совместимом виде обычно
   генерирует изображение "с нуля" по тексту. Наш сценарий — вставить лицо
   пользователя в новое фото (image-to-image), а для этого чаще нужен
   отдельный метод (`images.edit` / `images.edits`, либо кастомный формат
   конкретной модели). В `apps/photos/services/polza_client.py` уже есть
   обе функции — сверьтесь с актуальной документацией в личном кабинете
   Polza.ai для модели `google/gemini-3.1-flash-lite-image-preview` и
   поправьте вызов при необходимости (это единственное место в проекте,
   которое их использует).
2. **Базовый URL Polza.ai** в открытых источниках указывается
   по-разному (`https://polza.ai/api` и `https://api.polza.ai/api/v1`) —
   вынесен в `.env` как `POLZA_BASE_URL`, проверьте актуальное значение в
   вашем аккаунте.
3. **ACL бакета.** Сейчас код загружает результат с `ACL=public-read` для
   простоты (сразу получаем публичную ссылку). Для приватного контента
   (фото людей) разумнее сделать бакет приватным и отдавать пользователю
   presigned URL с ограниченным сроком жизни — правьте `services/storage.py`.
4. **Троттлинг.** В `settings.py` уже включён `AnonRateThrottle` (20 запросов
   в день для анонимов), чтобы не «утечь» бюджет на Polza.ai — при желании
   смените лимиты.
5. **Хранение исходных фото.** Сейчас лица пользователей физически лежат в
   `MEDIA_ROOT`. Учитывая, что это лица людей, стоит продумать: срок
   хранения, автоочистку (Celery beat таска), политику конфиденциальности.
6. **Модерация контента** — стоит добавить базовую проверку загружаемых фото
   (например, что на фото вообще есть лицо) до того, как тратить деньги на
   вызов Polza.ai.
