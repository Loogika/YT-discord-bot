import asyncio
import logging
import time
from typing import Any
from urllib.parse import urlparse

import yt_dlp

from loogika.config import (
    YTDL_SEARCH_OPTIONS,
    YTDL_STREAM_M4A_OPTIONS,
    YTDL_STREAM_OPTIONS,
    YTDL_STREAM_OPUS_OPTIONS,
)
from loogika.music.models import Stream, Track


logger = logging.getLogger(__name__)


def classify_extraction_error(error: Exception) -> str:
    message = str(error).lower()
    if any(marker in message for marker in ("winerror 10054", "timed out", "ssl", "transporterror")):
        return "z1"
    if "javascript runtime" in message or "ejs" in message:
        return "z2"
    if any(
        marker in message
        for marker in ("unsupported url", "no tracks found", "channel", "expected a video")
    ):
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
    async def search_tracks(
        self,
        query: str,
        requested_by: str,
        limit: int = 10,
        *,
        requested_by_id: int | None = None,
    ) -> tuple[Track, ...]:
        started_at = time.perf_counter()
        logger.info(
            "Track candidate search started",
            extra={
                "event": "track.candidates.search.started",
                "query_length": len(query),
                "candidate_limit": limit,
            },
        )
        try:
            data = await asyncio.to_thread(
                self._extract_collection,
                f"ytsearch{limit}:{query}",
                YTDL_SEARCH_OPTIONS,
            )
        except Exception as exc:
            logger.exception(
                "Track candidate search failed",
                extra={
                    "event": "track.candidates.search.failed",
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    "error_code": classify_extraction_error(exc),
                },
            )
            raise

        tracks = tuple(
            self._track_from_data(entry, requested_by, requested_by_id=requested_by_id)
            for entry in data.get("entries", ())
            if entry and self._is_video_candidate(entry)
        )
        if not tracks:
            raise RuntimeError("No playable video results found.")

        logger.info(
            "Track candidate search completed",
            extra={
                "event": "track.candidates.search.completed",
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
                "candidate_count": len(tracks),
            },
        )
        return tracks

    async def find_track(
        self,
        query: str,
        requested_by: str,
        *,
        requested_by_id: int | None = None,
    ) -> Track:
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
            data = await asyncio.to_thread(self._extract_one, query, YTDL_STREAM_OPTIONS)
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
        track = self._track_from_data(
            data,
            requested_by,
            requested_by_id=requested_by_id,
            fallback_url=query,
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

    async def resolve_stream(self, track: Track, strategy: str = "opus") -> Stream:
        started_at = time.perf_counter()
        stream_options = {
            "opus": YTDL_STREAM_OPUS_OPTIONS,
            "m4a": YTDL_STREAM_M4A_OPTIONS,
        }.get(strategy)
        if stream_options is None:
            raise ValueError(f"Unknown stream strategy: {strategy}")
        logger.info(
            "Stream resolution started",
            extra={
                "event": "track.stream.resolve.started",
                "track_title": track.title,
                "stream_strategy": strategy,
            },
        )
        try:
            data = await asyncio.to_thread(
                self._extract_one,
                track.webpage_url,
                stream_options,
            )
        except Exception as exc:
            logger.exception(
                "Stream resolution failed",
                extra={
                    "event": "track.stream.resolve.failed",
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    "track_title": track.title,
                    "error_code": classify_extraction_error(exc),
                    "stream_strategy": strategy,
                },
            )
            raise
        stream_url = data.get("url")
        if not stream_url:
            raise RuntimeError("The audio stream URL is missing.")
        raw_headers = data.get("http_headers") or {}
        http_headers = tuple((str(key), str(value)) for key, value in raw_headers.items())
        stream = Stream(
            url=stream_url,
            strategy=strategy,
            format_id=data.get("format_id"),
            protocol=data.get("protocol"),
            audio_codec=data.get("acodec"),
            host=urlparse(stream_url).hostname,
            http_headers=http_headers,
        )
        logger.info(
            "Stream resolution completed",
            extra={
                "event": "track.stream.resolve.completed",
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
                "track_title": track.title,
                "stream_strategy": stream.strategy,
                "format_id": stream.format_id,
                "protocol": stream.protocol,
                "audio_codec": stream.audio_codec,
                "stream_host": stream.host,
            },
        )
        return stream

    @staticmethod
    def _extract_collection(query: str, base_options: dict[str, Any]) -> dict[str, Any]:
        options = {**base_options, "logger": YtdlpLogger()}
        with yt_dlp.YoutubeDL(options) as ytdl:
            data = ytdl.extract_info(query, download=False)

        if data is None:
            raise RuntimeError("No tracks found.")
        return data

    @classmethod
    def _extract_one(cls, query: str, base_options: dict[str, Any]) -> dict[str, Any]:
        data = cls._extract_collection(query, base_options)

        if "entries" in data:
            logger.info(
                "Direct extraction returned a non-video collection",
                extra={
                    "event": "track.extract.entries",
                    "result_type": data.get("_type"),
                    "extractor": data.get("extractor"),
                    "query_type": "url" if query.startswith(("http://", "https://")) else "text",
                },
            )
            raise RuntimeError(
                f"Expected a video but received {data.get('_type') or 'a collection'}."
            )

        return data

    @staticmethod
    def _is_video_candidate(data: dict[str, Any]) -> bool:
        result_type = data.get("_type")
        return result_type in {None, "url", "video"} and bool(
            data.get("webpage_url") or data.get("url")
        )

    @staticmethod
    def _track_from_data(
        data: dict[str, Any],
        requested_by: str,
        *,
        requested_by_id: int | None = None,
        fallback_url: str | None = None,
    ) -> Track:
        webpage_url = data.get("webpage_url") or data.get("url") or fallback_url
        if not webpage_url:
            raise RuntimeError("The track URL is missing.")
        return Track(
            title=data.get("title") or "Untitled",
            webpage_url=webpage_url,
            requested_by=requested_by,
            requested_by_id=requested_by_id,
            duration=int(data["duration"]) if data.get("duration") is not None else None,
            uploader=data.get("uploader") or data.get("channel"),
            thumbnail_url=data.get("thumbnail"),
        )
