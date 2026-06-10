import asyncio
import unittest

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

    def is_connected(self) -> bool:
        return True

    def is_playing(self) -> bool:
        return False

    def is_paused(self) -> bool:
        return False

    def stop(self) -> None:
        pass

    async def disconnect(self, *, force: bool = False) -> None:
        pass


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

    async def test_manager_returns_one_player_per_guild(self) -> None:
        manager = PlayerManager(FakeExtractor())  # type: ignore[arg-type]

        self.assertIs(manager.get(1), manager.get(1))
        self.assertIsNot(manager.get(1), manager.get(2))

        await manager.close()


if __name__ == "__main__":
    unittest.main()
