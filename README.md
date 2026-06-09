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

## Command

`/play query`

`query` can be a YouTube URL or search text. The bot joins your current voice channel and starts playing the found audio stream.

## Discord Developer Portal

Enable these OAuth2 scopes when inviting the bot:

- `bot`
- `applications.commands`

Bot permissions needed for this skeleton:

- Connect
- Speak
