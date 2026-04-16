FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python healthcheck.py

CMD ["python", "main.py"]
