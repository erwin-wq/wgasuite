FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system --gid 10001 wgasuite \
    && useradd --system --uid 10001 --gid wgasuite --home-dir /nonexistent --shell /usr/sbin/nologin wgasuite \
    && install -d -m 0700 -o wgasuite -g wgasuite /var/lib/wgasuite/google-credentials

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

USER wgasuite

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
