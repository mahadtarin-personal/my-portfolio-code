FROM python:3.12-slim
WORKDIR /app
COPY libs/kafka_shared /libs/kafka_shared
COPY libs/logging_shared /libs/logging_shared
COPY libs/tracing_shared /libs/tracing_shared
COPY libs/metrics_shared /libs/metrics_shared
COPY services/analytics/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/analytics/app ./app
COPY services/analytics/alembic ./alembic
COPY services/analytics/alembic.ini .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
