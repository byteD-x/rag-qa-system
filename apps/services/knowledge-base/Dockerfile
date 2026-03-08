FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/packages/python:/app/apps/services/knowledge-base/src

WORKDIR /app

COPY apps/services/knowledge-base/requirements.runtime.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY apps/services/knowledge-base /app/apps/services/knowledge-base
COPY packages/python /app/packages/python

WORKDIR /app/apps/services/knowledge-base/src

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
