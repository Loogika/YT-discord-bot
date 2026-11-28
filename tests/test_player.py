import asyncio
import shlex
import unittest
from unittest.mock import patch

from loogika.music.manager import PlayerManager
from loogika.music.models import Stream, Track
from loogika.music.player import (
    GuildPlayer,
    StartupTrackingSource,
    build_ffmpeg_before_options,
)


class FakeExtractor:
    def __init__(self) -> None:
        self.resolve_started = asyncio.Event()
        self.allow_resolve = asyncio.Event()
        self.strategies: list[str] = []

    async def find_track(
        self,
        query: str,
        requested_by: str,
        *,
        requested_by_id: int | None = None,
    ) -> Track:
        return Track(
            title=query,
            webpage_url=query,
            requested_by=requested_by,
            requested_by_id=requested_by_id,
        )

    async def resolve_stream(self, track: Track, strategy: str = "opus") -> Stream:
        self.strategies.append(strategy)
        self.resolve_started.set()
        await self.allow_resolve.wait()
        return Stream(
            url="stream-url",
            strategy=strategy,
            format_id="251" if strategy == "opus" else "140",
            protocol="https",
            audio_codec="opus" if strategy == "opus" else "mp4a.40.2",
            host="example.googlevideo.com",
        )


class FakeVoiceClient:
    def __init__(self) -> None:
        self.play_calls = 0
        self.play_started = asyncio.Event()
        self.playing = False

    def is_connected(self) -> bool:
        return True

    def is_playing(self) -> bool:
        return self.playing

    def is_paused(self) -> bool:
        return False

    def stop(self) -> None:
        self.playing = False

    def play(self, source: object, **kwargs: object) -> None:
        self.play_calls += 1
        self.playing = True
        self.play_started.set()

    async def disconnect(self, *, force: bool = False) -> None:
        pass


class FakeSource:
    def __init__(self, frame: bytes = b"") -> None:
        self.cleaned_up = False
        self.cleanup_calls = 0
        self.frame = frame

    def read(self) -> bytes:
        return self.frame

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        self.cleaned_up = True
        self.cleanup_calls += 1


class GuildPlayerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_during_resolution_prevents_playback(self) -> None:
        extractor = FakeExtractor()
        voice_client = FakeVoiceClient()
        player = GuildPlayer(1, extractor)  # type: ignore[arg-type]
        player.bind_voice_client(voice_client)  # type: ignore[arg-type]

        await player.enqueue("track", "user")
        await extractor.resolve_started.wait()

        self.assertTrue(player.stop())
        extractor.allow_resolve.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.assertEqual(voice_client.play_calls, 0)
        self.assertIsNone(player.current_track)
        await player.close()

    async def test_skip_cleans_up_blocked_ffmpeg_source(self) -> None:
        extractor = FakeExtractor()
        extractor.allow_resolve.set()
        voice_client = FakeVoiceClient()
        source = FakeSource()
        player = GuildPlayer(1, extractor)  # type: ignore[arg-type]
        player.bind_voice_client(voice_client)  # type: ignore[arg-type]

        with patch("loogika.music.player.discord.FFmpegPCMAudio", return_value=source):
            await player.enqueue("track", "user")
            await voice_client.play_started.wait()

            self.assertEqual(player.playback_state, "playing")
            self.assertTrue(player.skip())
            await asyncio.sleep(0.2)

        self.assertTrue(source.cleaned_up)
        self.assertFalse(voice_client.playing)
        self.assertIsNone(player.current_track)
        self.assertEqual(player.playback_state, "idle")
        await player.close()

    async def test_retries_when_ffmpeg_produces_no_audio_frames(self) -> None:
        extractor = FakeExtractor()
        extractor.allow_resolve.set()
        voice_client = FakeVoiceClient()
        player = GuildPlayer(1, extractor)  # type: ignore[arg-type]
        player.bind_voice_client(voice_client)  # type: ignore[arg-type]

        with (
            patch(
                "loogika.music.player.discord.FFmpegPCMAudio",
                side_effect=(FakeSource(), FakeSource()),
            ),
            patch("loogika.music.player.PLAYBACK_STARTUP_TIMEOUT_SECONDS", 0.01),
        ):
            await player.enqueue("track", "user")
            await asyncio.sleep(0.25)

        self.assertEqual(voice_client.play_calls, 2)
        self.assertEqual(extractor.strategies, ["opus", "m4a"])
        self.assertIsNone(player.current_track)
        self.assertEqual(player.playback_state, "idle")
        await player.close()

    async def test_manager_returns_one_player_per_guild(self) -> None:
        manager = PlayerManager(FakeExtractor())  # type: ignore[arg-type]

        self.assertIs(manager.get(1), manager.get(1))
        self.assertIsNot(manager.get(1), manager.get(2))

        await manager.close()

    async def test_startup_tracking_source_cleanup_is_idempotent(self) -> None:
        inner = FakeSource()
        wrapped = StartupTrackingSource(inner)  # type: ignore[arg-type]

        wrapped.cleanup()
        wrapped.cleanup()

        self.assertEqual(inner.cleanup_calls, 1)

    async def test_track_callbacks_fire_on_playback_start_and_skip(self) -> None:
        extractor = FakeExtractor()
        extractor.allow_resolve.set()
        voice_client = FakeVoiceClient()
        source = FakeSource(frame=b"pcm-data")
        player = GuildPlayer(1, extractor)  # type: ignore[arg-type]
        player.bind_voice_client(voice_client)  # type: ignore[arg-type]

        started_tracks: list[str] = []
        finished_events: list[tuple[str, bool]] = []

        async def on_started(track: Track, _effect: object) -> None:
            started_tracks.append(track.title)

        async def on_finished(track: Track, was_skipped: bool) -> None:
            finished_events.append((track.title, was_skipped))

        player.set_callbacks(on_track_started=on_started, on_track_finished=on_finished)

        with patch("loogika.music.player.discord.FFmpegPCMAudio", return_value=source):
            await player.enqueue("track-1", "alice", requested_by_id=42)
            await voice_client.play_started.wait()
            # Simulate audio frame read so startup completes and on_started fires.
            assert player._active_source is not None
            player._active_source.read()
            await asyncio.sleep(0.15)

            self.assertEqual(started_tracks, ["track-1"])
            self.assertTrue(player.skip())
            await asyncio.sleep(0.05)

        self.assertEqual(finished_events, [("track-1", True)])
        await player.close()

    def test_build_ffmpeg_before_options_includes_http_headers(self) -> None:
        result = build_ffmpeg_before_options(
            "-reconnect 1",
            (("User-Agent", "Mozilla/5.0"), ("Accept", "*/*")),
        )
        tokens = shlex.split(result)

        self.assertEqual(
            tokens,
            [
                "-reconnect",
                "1",
                "-user_agent",
                "Mozilla/5.0",
                "-headers",
                "Accept: */*\r\n",
            ],
        )


if __name__ == "__main__":
    unittest.main()
