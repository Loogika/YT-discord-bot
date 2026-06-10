import logging

import discord
from discord.ext import commands

from loogika.config import Settings
from loogika.music.extractor import TrackExtractor
from loogika.music.manager import PlayerManager


logger = logging.getLogger(__name__)


class LoogikaBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(command_prefix="!", intents=intents)

        self.settings = settings
        self.players = PlayerManager(TrackExtractor())

    async def setup_hook(self) -> None:
        await self.load_extension("loogika.cogs.music")

        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(
                "Slash commands synchronized",
                extra={
                    "event": "bot.commands.synced",
                    "command_count": len(synced),
                    "guild_id": self.settings.guild_id,
                },
            )
        else:
            synced = await self.tree.sync()
            logger.info(
                "Global slash commands synchronized",
                extra={
                    "event": "bot.commands.synced",
                    "command_count": len(synced),
                },
            )

    async def on_ready(self) -> None:
        logger.info(
            "Bot is ready",
            extra={
                "event": "bot.ready",
                "bot_user": str(self.user),
                "guild_count": len(self.guilds),
            },
        )

    async def close(self) -> None:
        await self.players.close()
        await super().close()
