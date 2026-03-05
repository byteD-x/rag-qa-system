FROM python:3.10-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.runtime.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.runtime.txt

COPY worker ./worker

CMD ["python", "-m", "worker.main"]
