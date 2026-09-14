# Stub service — health check only, real billing logic is a later phase.
FROM python:3.12-slim
WORKDIR /app
COPY libs/logging_shared /libs/logging_shared
COPY libs/tracing_shared /libs/tracing_shared
COPY libs/metrics_shared /libs/metrics_shared
COPY services/billing/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/billing/app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
