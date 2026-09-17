FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=1 \
    MALLOC_ARENA_MAX=2
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker worker
COPY backend backend
RUN mkdir -p data
CMD ["python", "worker/worker.py"]
