import logging
from collections.abc import Awaitable, Callable

import discord

from loogika.music.models import Track


logger = logging.getLogger(__name__)

TrackSelectionHandler = Callable[[discord.Interaction, Track], Awaitable[None]]


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes}:{remaining_seconds:02d}"


def build_search_embed(query: str, tracks: tuple[Track, ...]) -> discord.Embed:
    embed = discord.Embed(
        title="Choose a track",
        description=f"Search results for **{query[:200]}**",
        color=discord.Color.blurple(),
    )
    for index, track in enumerate(tracks, start=1):
        details = " · ".join(
            value
            for value in (track.uploader, format_duration(track.duration))
            if value
        )
        embed.add_field(
            name=f"{index}. {track.title[:240]}",
            value=f"[Open on YouTube]({track.webpage_url}) · {details}",
            inline=False,
        )
    embed.set_footer(text="Only the user who ran /play can choose a track.")
    return embed


class TrackSelect(discord.ui.Select):
    def __init__(self, tracks: tuple[Track, ...]) -> None:
        options = [
            discord.SelectOption(
                label=track.title[:100],
                description=f"{track.uploader or 'Unknown'} · {format_duration(track.duration)}"[:100],
                value=str(index),
            )
            for index, track in enumerate(tracks)
        ]
        super().__init__(
            placeholder="Select a track to play",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TrackSearchView):
            return
        await view.select_track(interaction, int(self.values[0]))


class TrackSearchView(discord.ui.View):
    def __init__(
        self,
        requester_id: int,
        tracks: tuple[Track, ...],
        on_select: TrackSelectionHandler,
    ) -> None:
        super().__init__(timeout=60)
        self.requester_id = requester_id
        self.tracks = tracks
        self.on_select = on_select
        self.message: discord.Message | None = None
        self.add_item(TrackSelect(tracks))

    def disable_components(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Select):
                item.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message(
            "Only the user who ran /play can choose a track.",
            ephemeral=True,
        )
        return False

    async def select_track(self, interaction: discord.Interaction, index: int) -> None:
        await interaction.response.defer()
        try:
            await interaction.delete_original_response()
            self.message = None
        except discord.HTTPException:
            self.disable_components()
            await interaction.edit_original_response(view=self)
        self.stop()

        track = self.tracks[index]
        logger.info(
            "Search result selected",
            extra={
                "event": "track.candidates.selected",
                "guild_id": interaction.guild_id,
                "user_id": interaction.user.id,
                "track_title": track.title,
                "selection_index": index,
            },
        )
        await self.on_select(interaction, track)

    async def on_timeout(self) -> None:
        self.disable_components()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
