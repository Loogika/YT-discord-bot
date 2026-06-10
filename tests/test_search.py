import unittest
from unittest.mock import patch

from loogika.cogs.music_search import build_search_embed, format_duration
from loogika.music.extractor import TrackExtractor
from loogika.music.models import Track


class TrackSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_filters_non_video_entries(self) -> None:
        extractor = TrackExtractor()
        result = {
            "entries": [
                {
                    "_type": "url",
                    "title": "Playable",
                    "url": "https://www.youtube.com/watch?v=abc",
                    "duration": 125,
                },
                {
                    "_type": "playlist",
                    "title": "Channel",
                    "url": "https://www.youtube.com/channel/example",
                },
            ]
        }

        with patch.object(TrackExtractor, "_extract_collection", return_value=result):
            tracks = await extractor.search_tracks("query", "user")

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].title, "Playable")
        self.assertEqual(tracks[0].duration, 125)

    def test_direct_collection_is_rejected(self) -> None:
        result = {"_type": "playlist", "entries": [{"title": "Video"}]}

        with patch.object(TrackExtractor, "_extract_collection", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "Expected a video"):
                TrackExtractor._extract_one("https://example.com/channel", {})

    def test_search_embed_contains_one_field_per_track(self) -> None:
        tracks = tuple(
            Track(
                title=f"Track {index}",
                webpage_url=f"https://example.com/{index}",
                requested_by="user",
                duration=125,
            )
            for index in range(10)
        )

        embed = build_search_embed("query", tracks)

        self.assertEqual(len(embed.fields), 10)
        self.assertEqual(format_duration(125), "2:05")


if __name__ == "__main__":
    unittest.main()
