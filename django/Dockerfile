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

# Install requirements to /opt/venv to avoid volume mount overwriting
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/base.txt

COPY django/ .

# Copy entrypoint scripts (build context is project root)
COPY django/entrypoint.sh /app/entrypoint.sh
COPY django/celery_entrypoint.sh /app/celery_entrypoint.sh
RUN chmod +x /app/entrypoint.sh /app/celery_entrypoint.sh

RUN mkdir -p /app/staticfiles /app/media /app/logs

EXPOSE 8000

ENTRYPOINT ["sh", "entrypoint.sh"]
