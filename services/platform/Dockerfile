FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system guilddesk \
    && useradd --system --gid guilddesk --home-dir /srv/guilddesk guilddesk

WORKDIR /srv/guilddesk

COPY pyproject.toml uv.lock ./
COPY services/platform/pyproject.toml ./services/platform/pyproject.toml
COPY discord_bot/pyproject.toml ./discord_bot/pyproject.toml
COPY services/platform/app ./services/platform/app
COPY services/platform/alembic ./services/platform/alembic
COPY services/platform/alembic.ini ./services/platform/alembic.ini

RUN python -m pip install uv==0.9.22 \
    && uv sync --frozen --no-dev --package guilddesk-platform --no-editable \
    && chown -R guilddesk:guilddesk /srv/guilddesk

ENV PATH="/srv/guilddesk/.venv/bin:${PATH}"

WORKDIR /srv/guilddesk/services/platform

USER guilddesk

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
