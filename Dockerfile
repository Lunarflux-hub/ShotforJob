FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# fonts-noto-color-emoji — цветные эмодзи на слайдах каруселей
# (apps/carousels/services/renderer.py)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc netcat-openbsd fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Непривилегированный пользователь — не запускаем процесс в контейнере от root
RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R app:app /app
USER app

COPY --chown=app:app docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
