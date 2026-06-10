import asyncio
import logging
import time
from collections import deque

import discord

from loogika.config import FFMPEG_BEFORE_OPTIONS, FFMPEG_OPTIONS
from loogika.music.extractor import TrackExtractor
from loogika.music.models import Track


logger = logging.getLogger(__name__)


class GuildPlayer:
    def __init__(self, guild_id: int, extractor: TrackExtractor) -> None:
        self.guild_id = guild_id
        self.extractor = extractor
        self.current_track: Track | None = None

        self._queue: deque[Track] = deque()
        self._voice_client: discord.VoiceClient | None = None
        self._queue_ready = asyncio.Event()
        self._worker_task: asyncio.Task[None] | None = None
        self._cancel_current = False

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

    async def enqueue(self, query: str, requested_by: str) -> tuple[Track, int]:
        track = await self.extractor.find_track(query, requested_by)
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

    def skip(self) -> bool:
        voice_client = self._voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            logger.info(
                "Current track skipped",
                extra={"event": "playback.skipped", "guild_id": self.guild_id},
            )
            return True
        if self.current_track is None:
            return False
        self._cancel_current = True
        logger.info(
            "Resolving track skipped",
            extra={"event": "playback.skipped", "guild_id": self.guild_id},
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
        if self._voice_client and (
            self._voice_client.is_playing() or self._voice_client.is_paused()
        ):
            self._voice_client.stop()
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
                try:
                    await self._play(track)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "Track playback failed",
                        extra={
                            "event": "playback.failed",
                            "guild_id": self.guild_id,
                            "track_title": track.title,
                        },
                    )
                finally:
                    self.current_track = None

            self._queue_ready.clear()

    async def _play(self, track: Track) -> None:
        started_at = time.perf_counter()
        stream_url = await self.extractor.resolve_stream(track)
        if self._cancel_current:
            return

        voice_client = self._voice_client
        if voice_client is None or not voice_client.is_connected():
            raise RuntimeError("The voice client is not connected.")

        source = discord.FFmpegPCMAudio(
            stream_url,
            before_options=FFMPEG_BEFORE_OPTIONS,
            options=FFMPEG_OPTIONS,
        )
        playback_finished = asyncio.Event()
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
            voice_client.play(source, after=after_playback)
            logger.info(
                "Track playback started",
                extra={
                    "event": "playback.started",
                    "guild_id": self.guild_id,
                    "track_title": track.title,
                },
            )
        except Exception:
            source.cleanup()
            raise
        await playback_finished.wait()
        logger.info(
            "Track playback finished",
            extra={
                "event": "playback.finished",
                "guild_id": self.guild_id,
                "track_title": track.title,
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
            },
        )
