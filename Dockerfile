FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

ENV IKUAI_BACKUP_DATA_DIR=/data \
    IKUAI_BACKUP_DIR=/backups \
    IKUAI_BACKUP_HOST=0.0.0.0 \
    IKUAI_BACKUP_PORT=5000 \
    IKUAI_BACKUP_USE_WAITRESS=true

VOLUME ["/data", "/backups"]

CMD ["python", "run.py"]
