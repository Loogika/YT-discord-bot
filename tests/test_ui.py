import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from loogika.cogs.music_ui import NowPlayingView, build_now_playing_embed, format_requester
from loogika.music.models import Track


class MusicUiTests(unittest.IsolatedAsyncioTestCase):
    def test_format_requester_prefers_user_mention(self) -> None:
        track_with_id = Track(
            title="Song",
            webpage_url="https://example.com/song",
            requested_by="Alice",
            requested_by_id=123456,
        )
        track_without_id = Track(
            title="Song",
            webpage_url="https://example.com/song",
            requested_by="Alice",
        )

        self.assertEqual(format_requester(track_with_id), "<@123456>")
        self.assertEqual(format_requester(track_without_id), "Alice")

    def test_build_now_playing_embed_includes_requester_and_effect(self) -> None:
        track = Track(
            title="Test Track",
            webpage_url="https://example.com/watch?v=1",
            requested_by="Alice",
            requested_by_id=999,
            duration=185,
        )

        embed = build_now_playing_embed(track, "radio")
        fields = {field.name: field.value for field in embed.fields}

        self.assertEqual(embed.title, "Playing")
        self.assertIn("Test Track", embed.description or "")
        self.assertEqual(fields["Requested by"], "<@999>")
        self.assertEqual(fields["Duration"], "3:05")
        self.assertEqual(fields["Effect"], "radio")

    async def test_now_playing_view_rejects_user_outside_voice_channel(self) -> None:
        on_skip = AsyncMock(return_value=True)
        view = NowPlayingView(on_skip=on_skip)
        interaction = SimpleNamespace(
            guild=SimpleNamespace(voice_client=SimpleNamespace(channel=object())),
            user=SimpleNamespace(voice=None),
            response=SimpleNamespace(send_message=AsyncMock()),
        )

        allowed = await view.interaction_check(interaction)  # type: ignore[arg-type]

        self.assertFalse(allowed)
        interaction.response.send_message.assert_awaited_once()
        on_skip.assert_not_awaited()

    async def test_now_playing_view_skip_button_calls_handler_and_disables(self) -> None:
        on_skip = AsyncMock(return_value=True)
        view = NowPlayingView(on_skip=on_skip)
        skip_button = next(
            child for child in view.children if isinstance(child, discord.ui.Button)
        )
        embed = discord.Embed(title="Playing")
        interaction = SimpleNamespace(
            user=SimpleNamespace(display_name="Alice"),
            message=SimpleNamespace(embeds=[embed]),
            response=SimpleNamespace(edit_message=AsyncMock(), defer=AsyncMock()),
        )

        await skip_button.callback(interaction)  # type: ignore[arg-type]

        on_skip.assert_awaited_once_with(interaction)
        self.assertTrue(skip_button.disabled)
        self.assertTrue(view.is_finished())
        interaction.response.edit_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
