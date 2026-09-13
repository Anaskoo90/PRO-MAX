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

RUN python -m pip install uv==0.9.22 \
    && uv sync --frozen --no-dev --package guilddesk-discord-bot --no-install-project

COPY discord_bot/__init__.py discord_bot/bot.py discord_bot/client.py discord_bot/config.py ./discord_bot/
COPY discord_bot/cogs ./discord_bot/cogs
COPY discord_bot/services ./discord_bot/services
COPY discord_bot/utils ./discord_bot/utils
COPY discord_bot/views ./discord_bot/views

RUN chown -R guilddesk:guilddesk /srv/guilddesk

ENV PATH="/srv/guilddesk/.venv/bin:${PATH}"

USER guilddesk

CMD ["python", "-m", "discord_bot.bot"]
