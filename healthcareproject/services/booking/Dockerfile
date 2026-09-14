FROM python:3.12-slim
WORKDIR /app
COPY libs/jwt_shared /libs/jwt_shared
COPY libs/kafka_shared /libs/kafka_shared
COPY libs/logging_shared /libs/logging_shared
COPY libs/tracing_shared /libs/tracing_shared
COPY libs/metrics_shared /libs/metrics_shared
COPY libs/rate_limit_shared /libs/rate_limit_shared
COPY services/booking/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/booking/app ./app
COPY services/booking/alembic ./alembic
COPY services/booking/alembic.ini .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
