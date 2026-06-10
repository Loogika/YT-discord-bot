import unittest
from unittest.mock import patch

from loogika.cogs.music_search import build_search_embed, format_duration
from loogika.config import YTDL_STREAM_M4A_OPTIONS, YTDL_STREAM_OPUS_OPTIONS
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

    async def test_stream_strategy_selects_matching_format_options(self) -> None:
        extractor = TrackExtractor()
        track = Track(
            title="Track",
            webpage_url="https://www.youtube.com/watch?v=abc",
            requested_by="user",
        )
        result = {
            "url": "https://example.googlevideo.com/audio",
            "format_id": "140",
            "protocol": "https",
            "acodec": "mp4a.40.2",
        }

        with patch.object(TrackExtractor, "_extract_one", return_value=result) as extract:
            stream = await extractor.resolve_stream(track, "m4a")

        self.assertEqual(stream.strategy, "m4a")
        self.assertEqual(stream.format_id, "140")
        self.assertIs(extract.call_args.args[1], YTDL_STREAM_M4A_OPTIONS)
        self.assertIsNot(YTDL_STREAM_M4A_OPTIONS, YTDL_STREAM_OPUS_OPTIONS)


if __name__ == "__main__":
    unittest.main()
