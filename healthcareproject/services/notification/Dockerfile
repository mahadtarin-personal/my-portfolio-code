FROM python:3.12-slim
WORKDIR /app
COPY libs/kafka_shared /libs/kafka_shared
COPY libs/logging_shared /libs/logging_shared
COPY libs/tracing_shared /libs/tracing_shared
COPY libs/metrics_shared /libs/metrics_shared
COPY services/notification/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/notification/app ./app
COPY services/notification/alembic ./alembic
COPY services/notification/alembic.ini .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
