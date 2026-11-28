import logging
from collections.abc import Awaitable, Callable

import discord

from loogika.music.models import Track


logger = logging.getLogger(__name__)

SkipHandler = Callable[[discord.Interaction], Awaitable[bool]]


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes}:{remaining_seconds:02d}"


def format_requester(track: Track) -> str:
    if track.requested_by_id is not None:
        return f"<@{track.requested_by_id}>"
    return track.requested_by


def build_now_playing_embed(
    track: Track,
    effect_name: str,
    *,
    status: str = "Playing",
) -> discord.Embed:
    embed = discord.Embed(
        title=status,
        description=f"[{track.title}]({track.webpage_url})",
        color=discord.Color.green() if status == "Playing" else discord.Color.blurple(),
    )
    embed.add_field(name="Requested by", value=format_requester(track), inline=True)
    if track.duration is not None:
        embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
    embed.add_field(name="Effect", value=effect_name, inline=True)
    if track.thumbnail_url:
        embed.set_thumbnail(url=track.thumbnail_url)
    return embed


class NowPlayingView(discord.ui.View):
    def __init__(self, on_skip: SkipHandler) -> None:
        super().__init__(timeout=None)
        self.on_skip = on_skip
        self.message: discord.Message | None = None
        self._skipped = False

    def disable_components(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def disable_message(self) -> None:
        self.disable_components()
        self.stop()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
            self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False
        voice_client = interaction.guild.voice_client
        user_voice = getattr(interaction.user, "voice", None)
        if (
            voice_client is not None
            and user_voice is not None
            and user_voice.channel == voice_client.channel
        ):
            return True
        await interaction.response.send_message(
            "Join the bot's voice channel to skip tracks.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Skip", emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button["NowPlayingView"],
    ) -> None:
        if self._skipped:
            await interaction.response.defer()
            return

        self._skipped = True
        self.disable_components()
        self.stop()

        skipped = await self.on_skip(interaction)
        embeds = list(interaction.message.embeds) if interaction.message else []
        if embeds:
            footer_text = (
                f"Skipped by {interaction.user.display_name}"
                if skipped
                else "Nothing is playing."
            )
            embeds[0].set_footer(text=footer_text)

        try:
            await interaction.response.edit_message(embeds=embeds, view=self)
        except discord.HTTPException:
            pass
        self.message = None
