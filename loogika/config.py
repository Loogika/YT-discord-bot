import os
from dataclasses import dataclass

from dotenv import load_dotenv


YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}

FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


@dataclass(frozen=True)
class Settings:
    token: str
    guild_id: int | None
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise RuntimeError("DISCORD_TOKEN is not set. Create .env from .env.example.")

        guild_id = os.getenv("DISCORD_GUILD_ID")
        return cls(
            token=token,
            guild_id=int(guild_id) if guild_id else None,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
