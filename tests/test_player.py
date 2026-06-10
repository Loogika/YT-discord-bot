import asyncio
import unittest
from unittest.mock import patch

from loogika.music.manager import PlayerManager
from loogika.music.models import Track
from loogika.music.player import GuildPlayer


class FakeExtractor:
    def __init__(self) -> None:
        self.resolve_started = asyncio.Event()
        self.allow_resolve = asyncio.Event()

    async def find_track(self, query: str, requested_by: str) -> Track:
        return Track(title=query, webpage_url=query, requested_by=requested_by)

    async def resolve_stream(self, track: Track) -> str:
        self.resolve_started.set()
        await self.allow_resolve.wait()
        return "stream-url"


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
    def __init__(self) -> None:
        self.cleaned_up = False

    def cleanup(self) -> None:
        self.cleaned_up = True


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
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        self.assertTrue(source.cleaned_up)
        self.assertFalse(voice_client.playing)
        self.assertIsNone(player.current_track)
        self.assertEqual(player.playback_state, "idle")
        await player.close()

    async def test_manager_returns_one_player_per_guild(self) -> None:
        manager = PlayerManager(FakeExtractor())  # type: ignore[arg-type]

        self.assertIs(manager.get(1), manager.get(1))
        self.assertIsNot(manager.get(1), manager.get(2))

        await manager.close()


if __name__ == "__main__":
    unittest.main()
