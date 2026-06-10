from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    title: str
    webpage_url: str
    requested_by: str
    duration: int | None = None
    uploader: str | None = None
    thumbnail_url: str | None = None


@dataclass(frozen=True)
class Stream:
    url: str
    strategy: str
    format_id: str | None
    protocol: str | None
    audio_codec: str | None
    host: str | None
