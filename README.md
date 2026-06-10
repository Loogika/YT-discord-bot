# LoogikaBot

Minimal Discord music bot skeleton using `discord.py`, `yt-dlp`, and `ffmpeg`.

## Setup

1. Install Python 3.11+.
2. Install `ffmpeg` and make sure `ffmpeg.exe` is available in `PATH`.
3. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

4. Copy `.env.example` to `.env` and fill in:

```env
DISCORD_TOKEN=your_bot_token
DISCORD_GUILD_ID=your_test_server_id
```

5. Run:

```powershell
python bot.py
```

## Docker Compose

The runtime image contains Python, FFmpeg, Deno, and the yt-dlp EJS components.
This resolves the missing JavaScript runtime warning (`z2`) inside the container.

Build and start the bot:

```powershell
docker compose up --build -d
```

View logs:

```powershell
docker compose logs -f bot
```

Stop the bot:

```powershell
docker compose down
```

Grafana is available at [http://127.0.0.1:3000](http://127.0.0.1:3000).
The default username is `admin`; set `GRAFANA_ADMIN_PASSWORD` in `.env`.

The observability pipeline is:

```text
bot JSON stdout -> Docker logs -> Grafana Alloy -> Loki -> Grafana
```

Only containers with the `observability.logs=true` label are collected. Loki
keeps logs for seven days. Grafana, Loki, and Alloy data is persisted in Docker
volumes.

Useful Loki queries in Grafana Explore:

```logql
{compose_service="bot"}
{compose_service="bot", level="ERROR"}
{compose_service="bot", error_code="z4"}
{compose_service="bot", event="track.search.completed"} | json
```

On a VPS, port `3000` remains bound to localhost. Access it through an SSH
tunnel or place an authenticated HTTPS reverse proxy in front of Grafana.

The Dockerfile uses two stages:

- `builder` installs Python dependencies and downloads Deno
- `runtime` contains only the application runtime, FFmpeg, Deno, and certificates

The real `.env` file is passed by Compose at runtime and is excluded from the
Docker build context.

## Commands

- `/play query` - play a track or add it to the queue
- `/skip` - skip the current track
- `/pause` - pause playback
- `/resume` - resume playback
- `/stop` - stop playback and clear the queue
- `/queue` - show the current queue
- `/now-playing` - show the current track
- `/leave` - disconnect the bot

`query` can be a YouTube URL or search text. The bot joins your current voice channel and starts playing the found audio stream.

## Project structure

- `bot.py` - application entry point
- `loogika/bot.py` - bot lifecycle and extension loading
- `loogika/cogs/` - flat slash commands
- `loogika/music/` - track extraction, queues, and playback
- `Dockerfile` - two-stage production image
- `compose.yaml` - local and VPS container orchestration
- `observability/` - Alloy, Loki, and provisioned Grafana configuration

## Discord Developer Portal

Enable these OAuth2 scopes when inviting the bot:

- `bot`
- `applications.commands`

Bot permissions needed for this skeleton:

- Connect
- Speak
