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
        super().__init__(command_prefix=commands.when_mentioned_or("!"), intents=intents)

        self.settings = settings
        self.players = PlayerManager(TrackExtractor())
        self._stale_commands_cleared = False

    async def setup_hook(self) -> None:
        await self.load_extension("loogika.cogs.music")
        self._register_admin_commands()
        await self.sync_app_commands(
            guild_id=self.settings.guild_id,
            clear_stale=self.settings.clear_stale_commands,
        )

    def _register_admin_commands(self) -> None:
        @self.command(name="sync")
        @commands.is_owner()
        async def sync_command(ctx: commands.Context["LoogikaBot"], scope: str = "auto") -> None:
            normalized = scope.strip().lower()
            if normalized not in {"auto", "guild", "global", "clear"}:
                await ctx.reply("Usage: `@LoogikaBot sync [auto|guild|global|clear]`")
                return

            if normalized == "clear":
                if ctx.guild is not None:
                    self.tree.clear_commands(guild=ctx.guild)
                    await self.tree.sync(guild=ctx.guild)
                if self.application_id is not None:
                    await self.http.bulk_upsert_global_commands(self.application_id, [])
                await ctx.reply("Cleared guild and global slash commands.")
                return

            if normalized == "guild":
                if ctx.guild is None:
                    await ctx.reply("`guild` scope can only be used inside a server.")
                    return
                target_guild_id: int | None = ctx.guild.id
            elif normalized == "global":
                target_guild_id = None
            else:
                target_guild_id = self.settings.guild_id

            synced = await self.sync_app_commands(
                guild_id=target_guild_id,
                clear_stale=True,
            )
            names = ", ".join(f"/{cmd.name}" for cmd in synced) or "none"
            target_label = f"guild `{target_guild_id}`" if target_guild_id else "global"
            await ctx.reply(f"Synced {len(synced)} commands ({target_label}): {names}")

    async def sync_app_commands(
        self,
        *,
        guild_id: int | None = None,
        clear_stale: bool = False,
    ) -> list[discord.app_commands.AppCommand]:
        if guild_id is not None:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            if clear_stale and self.application_id is not None:
                await self.http.bulk_upsert_global_commands(self.application_id, [])
                logger.info(
                    "Cleared global slash commands to avoid stale duplicates",
                    extra={
                        "event": "bot.commands.cleared_global",
                        "guild_id": guild_id,
                    },
                )
            logger.info(
                "Slash commands synchronized",
                extra={
                    "event": "bot.commands.synced",
                    "scope": "guild",
                    "command_count": len(synced),
                    "commands": [cmd.name for cmd in synced],
                    "guild_id": guild_id,
                },
            )
            return synced

        synced = await self.tree.sync()
        if clear_stale:
            for guild in self.guilds:
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
        logger.info(
            "Global slash commands synchronized",
            extra={
                "event": "bot.commands.synced",
                "scope": "global",
                "command_count": len(synced),
                "commands": [cmd.name for cmd in synced],
            },
        )
        return synced

    async def on_ready(self) -> None:
        if (
            self.settings.clear_stale_commands
            and not self.settings.guild_id
            and not self._stale_commands_cleared
        ):
            self._stale_commands_cleared = True
            for guild in self.guilds:
                try:
                    self.tree.clear_commands(guild=guild)
                    await self.tree.sync(guild=guild)
                except discord.HTTPException:
                    logger.warning(
                        "Failed to clear guild-scoped commands",
                        extra={"event": "bot.commands.clear_guild_failed", "guild_id": guild.id},
                    )

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
