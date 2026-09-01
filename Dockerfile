FROM python:3.12-slim

# Prevent .pyc files and force stdout/stderr to be unbuffered (so logs show
# up immediately in `docker logs`).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps first so this layer is cached unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# storage/db.py writes leads.db to /app/leads.db at runtime; compose mounts
# a volume there so data survives container recreation/rebuilds.
EXPOSE 3500

# Default (production) command: gunicorn WSGI server.
# docker-compose.dev.yml overrides this with the Flask dev server + reload.
CMD ["gunicorn", "--bind", "0.0.0.0:3500", "--workers", "2", "--timeout", "120", "app:app"]
