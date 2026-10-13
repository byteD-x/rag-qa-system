FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/packages/python:/app/apps/services/api-gateway/src

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple
COPY apps/services/api-gateway/requirements.runtime.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r /tmp/requirements.txt

COPY apps/services/api-gateway /app/apps/services/api-gateway
COPY packages/python /app/packages/python

WORKDIR /app/apps/services/api-gateway/src

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
