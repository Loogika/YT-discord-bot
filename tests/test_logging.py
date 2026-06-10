import json
import logging
import unittest

from loogika.logging import JsonFormatter


class JsonFormatterTests(unittest.TestCase):
    def test_formats_context_as_json(self) -> None:
        record = logging.LogRecord(
            name="loogika.music.player",
            level=logging.INFO,
            pathname=__file__,
            lineno=12,
            msg="Playback started",
            args=(),
            exc_info=None,
        )
        record.event = "playback.started"
        record.guild_id = 123

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["logger"], "loogika.music.player")
        self.assertEqual(payload["event"], "playback.started")
        self.assertEqual(payload["guild_id"], 123)
