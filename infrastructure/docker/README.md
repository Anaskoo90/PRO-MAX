# Local Docker runtime

From the repository root:

```powershell
docker compose -f infrastructure/docker/docker-compose.yml up --build -d
docker compose -f infrastructure/docker/docker-compose.yml ps
```

The migration container must exit successfully before the API starts. Swagger
is then available at <http://localhost:8000/docs>, and Mailpit at
<http://localhost:8025>.

The values in this Compose file are development-only. Deployed environments
must provide independent secrets through their secret manager.

The Discord bot is an optional profile because it requires credentials from
the Discord Developer Portal:

```powershell
$env:DISCORD_BOT_TOKEN = "..."
$env:DISCORD_APPLICATION_ID = "..."
docker compose -f infrastructure/docker/docker-compose.yml --profile bot up --build -d
```
