import logging
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from loogika.music.player import GuildPlayer

if TYPE_CHECKING:
    from loogika.bot import LoogikaBot


logger = logging.getLogger(__name__)


class MusicCog(commands.Cog):
    def __init__(self, bot: "LoogikaBot") -> None:
        self.bot = bot

    def _get_player(self, interaction: discord.Interaction) -> GuildPlayer | None:
        if interaction.guild is None:
            return None
        return self.bot.players.find(interaction.guild.id)

    async def _connect_player(
        self,
        interaction: discord.Interaction,
    ) -> GuildPlayer | None:
        if interaction.guild is None:
            await interaction.followup.send(
                "Music commands can only be used in a server.",
                ephemeral=True,
            )
            return None

        user_voice = getattr(interaction.user, "voice", None)
        if user_voice is None or user_voice.channel is None:
            await interaction.followup.send("Join a voice channel first.", ephemeral=True)
            return None

        voice_client = interaction.guild.voice_client
        if voice_client is None:
            started_at = time.perf_counter()
            logger.info(
                "Voice connection started",
                extra={
                    "event": "voice.connect.started",
                    "guild_id": interaction.guild.id,
                    "voice_channel_id": user_voice.channel.id,
                },
            )
            voice_client = await user_voice.channel.connect()
            logger.info(
                "Voice connection completed",
                extra={
                    "event": "voice.connect.completed",
                    "guild_id": interaction.guild.id,
                    "voice_channel_id": user_voice.channel.id,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                },
            )
        elif voice_client.channel != user_voice.channel:
            await voice_client.move_to(user_voice.channel)

        player = self.bot.players.get(interaction.guild.id)
        player.bind_voice_client(voice_client)
        return player

    @app_commands.command(
        name="play",
        description="Play audio from a YouTube URL or search query",
    )
    @app_commands.describe(query="YouTube link or search text")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        logger.info(
            "Play command received",
            extra={
                "event": "command.play.received",
                "interaction_id": interaction.id,
                "guild_id": interaction.guild_id,
                "user_id": interaction.user.id,
                "query_type": "url" if query.startswith(("http://", "https://")) else "text",
            },
        )

        try:
            player = await self._connect_player(interaction)
            if player is None:
                return

            track, tracks_ahead = await player.enqueue(
                query=query,
                requested_by=interaction.user.display_name,
            )
        except Exception as exc:
            logger.exception(
                "Play command failed",
                extra={
                    "event": "command.play.failed",
                    "interaction_id": interaction.id,
                    "guild_id": interaction.guild_id,
                },
            )
            await interaction.followup.send(
                f"Could not load track: {exc}",
                ephemeral=True,
            )
            return

        if tracks_ahead:
            await interaction.followup.send(
                f"Queued #{tracks_ahead}: [{track.title}]({track.webpage_url})"
            )
        else:
            await interaction.followup.send(
                f"Now playing: [{track.title}]({track.webpage_url})"
            )

    @app_commands.command(name="skip", description="Skip the current track")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction) -> None:
        player = self._get_player(interaction)
        if player is None or not player.skip():
            await interaction.response.send_message(
                "Nothing is playing.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Skipped.")

    @app_commands.command(name="pause", description="Pause the current track")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        player = self._get_player(interaction)
        if player is None or not player.pause():
            await interaction.response.send_message(
                "Nothing is playing.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Paused.")

    @app_commands.command(name="resume", description="Resume the paused track")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        player = self._get_player(interaction)
        if player is None or not player.resume():
            await interaction.response.send_message(
                "Nothing is paused.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Resumed.")

    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        player = self._get_player(interaction)
        if player is None or not player.stop():
            await interaction.response.send_message(
                "Nothing is playing or queued.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Playback stopped and queue cleared.")

    @app_commands.command(name="queue", description="Show the current music queue")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction) -> None:
        player = self._get_player(interaction)
        if player is None:
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return

        current = player.current_track
        queued = player.queue_snapshot()
        if current is None and not queued:
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return

        lines: list[str] = []
        if current:
            lines.append(f"Now: [{current.title}]({current.webpage_url})")
        lines.extend(
            f"{index}. [{track.title}]({track.webpage_url})"
            for index, track in enumerate(queued[:10], start=1)
        )
        if len(queued) > 10:
            lines.append(f"...and {len(queued) - 10} more.")

        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="now-playing", description="Show the current track")
    @app_commands.guild_only()
    async def now_playing(self, interaction: discord.Interaction) -> None:
        player = self._get_player(interaction)
        track = player.current_track if player else None
        if track is None:
            await interaction.response.send_message(
                "Nothing is playing.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Now playing: [{track.title}]({track.webpage_url})"
        )

    @app_commands.command(name="leave", description="Leave the voice channel")
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Music commands can only be used in a server.",
                ephemeral=True,
            )
            return

        disconnected = await self.bot.players.remove(interaction.guild.id)
        if not disconnected:
            await interaction.response.send_message(
                "I am not connected to a voice channel.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Disconnected.")


async def setup(bot: "LoogikaBot") -> None:
    await bot.add_cog(MusicCog(bot))
