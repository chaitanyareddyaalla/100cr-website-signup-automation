FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker worker
COPY backend backend
RUN mkdir -p data
CMD ["python", "worker/worker.py"]
