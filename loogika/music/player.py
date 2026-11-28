import asyncio
import logging
import shlex
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable

import discord

from loogika.config import FFMPEG_BEFORE_OPTIONS, FFMPEG_OPTIONS
from loogika.music.effects import AudioEffect, DEFAULT_AUDIO_EFFECT
from loogika.music.extractor import TrackExtractor
from loogika.music.models import Stream, Track


logger = logging.getLogger(__name__)

PLAYBACK_STARTUP_TIMEOUT_SECONDS = 10
PLAYBACK_ATTEMPTS = 2


TrackStartedCallback = Callable[[Track, AudioEffect], Awaitable[None]]
TrackFinishedCallback = Callable[[Track, bool], Awaitable[None]]
TrackFailedCallback = Callable[[Track, Exception], Awaitable[None]]


def build_ffmpeg_before_options(
    base_options: str,
    http_headers: tuple[tuple[str, str], ...],
) -> str:
    parts = [base_options] if base_options else []
    user_agent: str | None = None
    other_headers: list[str] = []

    for key, value in http_headers:
        clean_value = value.replace("\r", "").replace("\n", "")
        if key.lower() == "user-agent":
            user_agent = clean_value
        else:
            other_headers.append(f"{key}: {clean_value}")

    if user_agent:
        parts.append(f"-user_agent {shlex.quote(user_agent)}")
    if other_headers:
        header_blob = "\r\n".join(other_headers) + "\r\n"
        parts.append(f"-headers {shlex.quote(header_blob)}")

    return " ".join(parts)


class StartupTrackingSource(discord.AudioSource):
    def __init__(self, source: discord.AudioSource) -> None:
        self.source = source
        self.first_frame = threading.Event()
        self._cleanup_lock = threading.Lock()
        self._cleaned_up = False

    def read(self) -> bytes:
        data = self.source.read()
        if data:
            self.first_frame.set()
        return data

    def is_opus(self) -> bool:
        return self.source.is_opus()

    def cleanup(self) -> None:
        with self._cleanup_lock:
            if self._cleaned_up:
                return
            self._cleaned_up = True
        self.source.cleanup()


class PlaybackStartupError(RuntimeError):
    pass


class GuildPlayer:
    def __init__(self, guild_id: int, extractor: TrackExtractor) -> None:
        self.guild_id = guild_id
        self.extractor = extractor
        self.current_track: Track | None = None
        self.audio_effect = DEFAULT_AUDIO_EFFECT

        self._queue: deque[Track] = deque()
        self._voice_client: discord.VoiceClient | None = None
        self._queue_ready = asyncio.Event()
        self._worker_task: asyncio.Task[None] | None = None
        self._cancel_current = False
        self._active_source: discord.AudioSource | None = None
        self._playback_finished: asyncio.Event | None = None
        self._on_track_started: TrackStartedCallback | None = None
        self._on_track_finished: TrackFinishedCallback | None = None
        self._on_track_failed: TrackFailedCallback | None = None
        self._track_started_emitted = False
        self.playback_state = "idle"

    def set_callbacks(
        self,
        *,
        on_track_started: TrackStartedCallback | None = None,
        on_track_finished: TrackFinishedCallback | None = None,
        on_track_failed: TrackFailedCallback | None = None,
    ) -> None:
        self._on_track_started = on_track_started
        self._on_track_finished = on_track_finished
        self._on_track_failed = on_track_failed

    def is_paused(self) -> bool:
        return bool(self._voice_client and self._voice_client.is_paused())

    def bind_voice_client(self, voice_client: discord.VoiceClient) -> None:
        self._voice_client = voice_client
        logger.info(
            "Voice client bound to player",
            extra={
                "event": "voice.client.bound",
                "guild_id": self.guild_id,
                "voice_channel_id": getattr(
                    getattr(voice_client, "channel", None),
                    "id",
                    None,
                ),
            },
        )
        self._ensure_worker()
        if self._queue:
            self._queue_ready.set()

    async def enqueue(
        self,
        query: str,
        requested_by: str,
        *,
        requested_by_id: int | None = None,
    ) -> tuple[Track, int]:
        track = await self.extractor.find_track(
            query,
            requested_by,
            requested_by_id=requested_by_id,
        )
        return self.enqueue_track(track)

    def enqueue_track(self, track: Track) -> tuple[Track, int]:
        tracks_ahead = len(self._queue) + (1 if self.current_track else 0)
        self._queue.append(track)
        self._queue_ready.set()
        self._ensure_worker()
        logger.info(
            "Track added to queue",
            extra={
                "event": "queue.track.added",
                "guild_id": self.guild_id,
                "track_title": track.title,
                "tracks_ahead": tracks_ahead,
                "queue_size": len(self._queue),
            },
        )
        return track, tracks_ahead

    def queue_snapshot(self) -> tuple[Track, ...]:
        return tuple(self._queue)

    def set_audio_effect(self, effect: AudioEffect) -> None:
        self.audio_effect = effect
        logger.info(
            "Audio effect changed",
            extra={
                "event": "audio.effect.changed",
                "guild_id": self.guild_id,
                "audio_effect": effect.name,
            },
        )

    def skip(self) -> bool:
        if self.current_track is None:
            return False

        self._cancel_current = True
        self._terminate_active_playback()
        logger.info(
            "Current track skipped",
            extra={
                "event": "playback.skipped",
                "guild_id": self.guild_id,
                "playback_state": self.playback_state,
            },
        )
        return True

    def pause(self) -> bool:
        voice_client = self._voice_client
        if voice_client is None or not voice_client.is_playing():
            return False
        voice_client.pause()
        logger.info(
            "Playback paused",
            extra={"event": "playback.paused", "guild_id": self.guild_id},
        )
        return True

    def resume(self) -> bool:
        voice_client = self._voice_client
        if voice_client is None or not voice_client.is_paused():
            return False
        voice_client.resume()
        logger.info(
            "Playback resumed",
            extra={"event": "playback.resumed", "guild_id": self.guild_id},
        )
        return True

    def stop(self) -> bool:
        had_tracks = bool(self.current_track or self._queue)
        self._queue.clear()
        self._cancel_current = True
        self._terminate_active_playback()
        if had_tracks:
            logger.info(
                "Playback stopped and queue cleared",
                extra={"event": "playback.stopped", "guild_id": self.guild_id},
            )
        return had_tracks

    async def close(self) -> bool:
        connected = self._voice_client is not None
        self.stop()

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

        if self._voice_client:
            await self._voice_client.disconnect(force=True)
            self._voice_client = None

        logger.info(
            "Guild player closed",
            extra={"event": "player.closed", "guild_id": self.guild_id},
        )
        return connected

    def _ensure_worker(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(
                self._playback_worker(),
                name=f"music-player-{self.guild_id}",
            )

    async def _playback_worker(self) -> None:
        while True:
            await self._queue_ready.wait()

            while (
                self._queue
                and self._voice_client
                and self._voice_client.is_connected()
            ):
                track = self._queue.popleft()
                self.current_track = track
                self._cancel_current = False
                self._track_started_emitted = False
                self.playback_state = "resolving"
                cancelled = False
                try:
                    await self._play(track)
                except asyncio.CancelledError:
                    cancelled = True
                    raise
                except Exception as exc:
                    logger.exception(
                        "Track playback failed",
                        extra={
                            "event": "playback.failed",
                            "guild_id": self.guild_id,
                            "track_title": track.title,
                        },
                    )
                    await self._emit_track_failed(track, exc)
                finally:
                    was_started = self._track_started_emitted
                    was_skipped = self._cancel_current
                    self._track_started_emitted = False
                    self.current_track = None
                    self.playback_state = "idle"
                    if was_started and not cancelled:
                        await self._emit_track_finished(track, was_skipped)

            self._queue_ready.clear()

    async def _play(self, track: Track) -> None:
        for attempt in range(1, PLAYBACK_ATTEMPTS + 1):
            strategy = "opus" if attempt == 1 else "m4a"
            try:
                await self._play_once(track, attempt, strategy)
                return
            except PlaybackStartupError:
                if self._cancel_current or attempt == PLAYBACK_ATTEMPTS:
                    raise
                logger.warning(
                    "Retrying track after playback startup failure",
                    extra={
                        "event": "playback.startup.retry",
                        "guild_id": self.guild_id,
                        "track_title": track.title,
                        "attempt": attempt + 1,
                        "stream_strategy": "m4a",
                    },
                )

    async def _play_once(self, track: Track, attempt: int, strategy: str) -> None:
        started_at = time.perf_counter()
        effect = self.audio_effect
        stream = await self.extractor.resolve_stream(track, strategy)
        if self._cancel_current:
            return

        voice_client = self._voice_client
        if voice_client is None or not voice_client.is_connected():
            raise RuntimeError("The voice client is not connected.")

        before_options = build_ffmpeg_before_options(
            FFMPEG_BEFORE_OPTIONS,
            stream.http_headers,
        )
        source = StartupTrackingSource(
            discord.FFmpegPCMAudio(
                stream.url,
                before_options=before_options,
                options=effect.ffmpeg_options(FFMPEG_OPTIONS),
            )
        )
        playback_finished = asyncio.Event()
        self._active_source = source
        self._playback_finished = playback_finished
        loop = asyncio.get_running_loop()

        def after_playback(error: Exception | None) -> None:
            if error:
                logger.error(
                    "FFmpeg playback callback reported an error",
                    extra={
                        "event": "playback.ffmpeg.error",
                        "guild_id": self.guild_id,
                        "track_title": track.title,
                        "error_code": "z4",
                        "error": str(error),
                        "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    },
                )
            loop.call_soon_threadsafe(playback_finished.set)

        try:
            voice_client.play(
                source,
                after=after_playback,
                bitrate=effect.opus_bitrate,
                bandwidth=effect.opus_bandwidth,
                application=effect.opus_application,
                signal_type=effect.opus_signal_type,
            )
            self.playback_state = "playing"
            logger.info(
                "Track playback started",
                extra={
                    "event": "playback.started",
                    "guild_id": self.guild_id,
                    "track_title": track.title,
                    "audio_effect": effect.name,
                    "opus_bitrate": effect.opus_bitrate,
                    "attempt": attempt,
                    **self._stream_log_context(stream),
                },
            )
        except Exception:
            source.cleanup()
            raise
        try:
            startup_deadline = (
                asyncio.get_running_loop().time() + PLAYBACK_STARTUP_TIMEOUT_SECONDS
            )
            while not source.first_frame.is_set() and not playback_finished.is_set():
                if asyncio.get_running_loop().time() >= startup_deadline:
                    logger.warning(
                        "FFmpeg did not produce an audio frame before the startup deadline",
                        extra={
                            "event": "playback.startup.timeout",
                            "guild_id": self.guild_id,
                            "track_title": track.title,
                            "attempt": attempt,
                            "timeout_seconds": PLAYBACK_STARTUP_TIMEOUT_SECONDS,
                            **self._stream_log_context(stream),
                        },
                    )
                    self._terminate_active_playback()
                    raise PlaybackStartupError(
                        "FFmpeg did not produce an audio frame before the startup deadline."
                    )
                await asyncio.sleep(0.1)

            if playback_finished.is_set() and self._cancel_current:
                return

            if playback_finished.is_set() and not source.first_frame.is_set():
                raise PlaybackStartupError(
                    "FFmpeg playback ended before producing an audio frame."
                )

            logger.info(
                "FFmpeg produced the first audio frame",
                extra={
                    "event": "playback.startup.completed",
                    "guild_id": self.guild_id,
                    "track_title": track.title,
                    "attempt": attempt,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    **self._stream_log_context(stream),
                },
            )
            await self._emit_track_started(track, effect)
            await playback_finished.wait()
        finally:
            if self._active_source is source:
                self._active_source = None
            if self._playback_finished is playback_finished:
                self._playback_finished = None
        logger.info(
            "Track playback finished",
            extra={
                "event": "playback.finished",
                "guild_id": self.guild_id,
                "track_title": track.title,
                "audio_effect": effect.name,
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
                "attempt": attempt,
                **self._stream_log_context(stream),
            },
        )

    async def _emit_track_started(self, track: Track, effect: AudioEffect) -> None:
        self._track_started_emitted = True
        if self._on_track_started is None:
            return
        try:
            await self._on_track_started(track, effect)
        except Exception:
            logger.exception(
                "Track started callback failed",
                extra={
                    "event": "playback.callback.started.failed",
                    "guild_id": self.guild_id,
                    "track_title": track.title,
                },
            )

    async def _emit_track_finished(self, track: Track, was_skipped: bool) -> None:
        if self._on_track_finished is None:
            return
        try:
            await self._on_track_finished(track, was_skipped)
        except Exception:
            logger.exception(
                "Track finished callback failed",
                extra={
                    "event": "playback.callback.finished.failed",
                    "guild_id": self.guild_id,
                    "track_title": track.title,
                },
            )

    async def _emit_track_failed(self, track: Track, error: Exception) -> None:
        if self._on_track_failed is None:
            return
        try:
            await self._on_track_failed(track, error)
        except Exception:
            logger.exception(
                "Track failed callback failed",
                extra={
                    "event": "playback.callback.failed.failed",
                    "guild_id": self.guild_id,
                    "track_title": track.title,
                },
            )

    @staticmethod
    def _stream_log_context(stream: Stream) -> dict[str, str | None]:
        return {
            "stream_strategy": stream.strategy,
            "format_id": stream.format_id,
            "protocol": stream.protocol,
            "audio_codec": stream.audio_codec,
            "stream_host": stream.host,
        }

    def _terminate_active_playback(self) -> None:
        voice_client = self._voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()

        source = self._active_source
        if source is not None:
            source.cleanup()
            self._active_source = None

        playback_finished = self._playback_finished
        if playback_finished is not None:
            playback_finished.set()
