import asyncio
import logging
import time
from typing import Any

import yt_dlp

from loogika.config import YTDL_OPTIONS
from loogika.music.models import Track


logger = logging.getLogger(__name__)


def classify_extraction_error(error: Exception) -> str:
    message = str(error).lower()
    if any(marker in message for marker in ("winerror 10054", "timed out", "ssl", "transporterror")):
        return "z1"
    if "javascript runtime" in message or "ejs" in message:
        return "z2"
    if any(marker in message for marker in ("unsupported url", "no tracks found", "channel")):
        return "z3"
    return "extraction_error"


class YtdlpLogger:
    def debug(self, message: str) -> None:
        logger.debug(message, extra={"event": "yt_dlp.debug"})

    def info(self, message: str) -> None:
        logger.info(message, extra={"event": "yt_dlp.info"})

    def warning(self, message: str) -> None:
        logger.warning(message, extra={"event": "yt_dlp.warning"})

    def error(self, message: str) -> None:
        logger.error(message, extra={"event": "yt_dlp.error"})


class TrackExtractor:
    async def find_track(self, query: str, requested_by: str) -> Track:
        started_at = time.perf_counter()
        logger.info(
            "Track search started",
            extra={
                "event": "track.search.started",
                "query_type": "url" if query.startswith(("http://", "https://")) else "text",
                "query_length": len(query),
            },
        )
        try:
            data = await asyncio.to_thread(self._extract, query)
        except Exception as exc:
            logger.exception(
                "Track search failed",
                extra={
                    "event": "track.search.failed",
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    "error_code": classify_extraction_error(exc),
                },
            )
            raise
        track = Track(
            title=data.get("title") or "Untitled",
            webpage_url=data.get("webpage_url") or query,
            requested_by=requested_by,
        )
        logger.info(
            "Track search completed",
            extra={
                "event": "track.search.completed",
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
                "track_title": track.title,
                "extractor": data.get("extractor"),
                "result_type": data.get("_type", "video"),
                "source_id": data.get("id"),
            },
        )
        return track

    async def resolve_stream(self, track: Track) -> str:
        started_at = time.perf_counter()
        logger.info(
            "Stream resolution started",
            extra={
                "event": "track.stream.resolve.started",
                "track_title": track.title,
            },
        )
        try:
            data = await asyncio.to_thread(self._extract, track.webpage_url)
        except Exception as exc:
            logger.exception(
                "Stream resolution failed",
                extra={
                    "event": "track.stream.resolve.failed",
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    "track_title": track.title,
                    "error_code": classify_extraction_error(exc),
                },
            )
            raise
        stream_url = data.get("url")
        if not stream_url:
            raise RuntimeError("The audio stream URL is missing.")
        logger.info(
            "Stream resolution completed",
            extra={
                "event": "track.stream.resolve.completed",
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
                "track_title": track.title,
                "format_id": data.get("format_id"),
                "protocol": data.get("protocol"),
                "audio_codec": data.get("acodec"),
            },
        )
        return stream_url

    @staticmethod
    def _extract(query: str) -> dict[str, Any]:
        options = {**YTDL_OPTIONS, "logger": YtdlpLogger()}
        with yt_dlp.YoutubeDL(options) as ytdl:
            data = ytdl.extract_info(query, download=False)

        if data is None:
            raise RuntimeError("No tracks found.")

        if "entries" in data:
            logger.info(
                "Extractor returned an entry collection",
                extra={
                    "event": "track.extract.entries",
                    "result_type": data.get("_type"),
                    "extractor": data.get("extractor"),
                    "query_type": "url" if query.startswith(("http://", "https://")) else "text",
                },
            )
            entry = next((item for item in data["entries"] if item), None)
            if entry is None:
                raise RuntimeError("No tracks found.")
            data = entry

        return data
