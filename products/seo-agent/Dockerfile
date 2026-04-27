FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Tokyo

RUN apt-get update && apt-get install -y --no-install-recommends \
        cron \
        tzdata \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/reports /app/credentials

COPY docker/crontab /etc/cron.d/seo-agent
RUN chmod 0644 /etc/cron.d/seo-agent && crontab /etc/cron.d/seo-agent

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
