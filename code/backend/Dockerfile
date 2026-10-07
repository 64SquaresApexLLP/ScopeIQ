# ScopeIQ backend image: API (default) or pipeline job. Used for Snowpark Container Services (SPCS) or any container host.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app/code/backend
COPY backend/requirements.txt backend/requirements-snowflake.txt ./
RUN pip install --no-cache-dir -r requirements-snowflake.txt
COPY reference_data /app/code/reference_data
COPY backend /app/code/backend
ENV SCOPEIQ_ENV=prod PYTHONUNBUFFERED=1
EXPOSE 8000
# API:            docker run -p 8000:8000 scopeiq
# Pipeline job:   docker run scopeiq python scripts/run_pipeline.py --backend snowflake
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
