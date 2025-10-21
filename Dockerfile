FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN mkdir -p /app/downloads /app/static /app/templates

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY templates ./templates
COPY static ./static
COPY report_templates ./report_templates

ENV PORT=10000
ENV OUTPUT_DIR=/app/downloads

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
