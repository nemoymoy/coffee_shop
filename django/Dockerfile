# django/Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY ../requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY . .

RUN mkdir -p /app/staticfiles /app/media /app/logs

EXPOSE 8000

ENTRYPOINT ["sh", "django/entrypoint.sh"]
