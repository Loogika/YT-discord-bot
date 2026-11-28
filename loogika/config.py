import os
from dataclasses import dataclass

from dotenv import load_dotenv


YTDL_BASE_OPTIONS = {
    "noplaylist": True,
    "quiet": True,
    "source_address": "0.0.0.0",
    "socket_timeout": 20,
    "retries": 3,
    "fragment_retries": 3,
}

YTDL_SEARCH_OPTIONS = {
    **YTDL_BASE_OPTIONS,
    "extract_flat": "in_playlist",
    "skip_download": True,
}

YTDL_STREAM_OPUS_OPTIONS = {
    **YTDL_BASE_OPTIONS,
    "format": "bestaudio[acodec=opus][protocol^=http]/bestaudio[protocol^=http][vcodec=none]/bestaudio/best",
    "skip_download": True,
}

YTDL_STREAM_M4A_OPTIONS = {
    **YTDL_BASE_OPTIONS,
    "format": "bestaudio[vcodec=none]/bestaudio/best",
    "extractor_args": {"youtube": {"player_client": ["web_safari", "android"]}},
    "skip_download": True,
}

YTDL_STREAM_OPTIONS = YTDL_STREAM_OPUS_OPTIONS

FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


@dataclass(frozen=True)
class Settings:
    token: str
    guild_id: int | None
    log_level: str = "INFO"
    clear_stale_commands: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise RuntimeError("DISCORD_TOKEN is not set. Create .env from .env.example.")

        guild_id = os.getenv("DISCORD_GUILD_ID")
        clear_stale = os.getenv("DISCORD_CLEAR_STALE_COMMANDS", "true").strip().lower()
        return cls(
            token=token,
            guild_id=int(guild_id) if guild_id else None,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            clear_stale_commands=clear_stale not in {"0", "false", "no", "off"},
        )
