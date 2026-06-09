import asyncio
import logging
import os
from dataclasses import dataclass

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}

FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


@dataclass(frozen=True)
class Track:
    title: str
    webpage_url: str
    stream_url: str


intents = discord.Intents.default()
intents.message_content = False
bot = commands.Bot(command_prefix="!", intents=intents)
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


async def extract_track(query: str) -> Track:
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))

    if "entries" in data:
        data = next((entry for entry in data["entries"] if entry), None)
        if data is None:
            raise RuntimeError("No tracks found.")

    return Track(
        title=data.get("title") or "Untitled",
        webpage_url=data.get("webpage_url") or query,
        stream_url=data["url"],
    )


@bot.event
async def on_ready() -> None:
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        logging.info("Synced %s command(s) to guild %s", len(synced), GUILD_ID)
    else:
        synced = await bot.tree.sync()
        logging.info("Synced %s global command(s)", len(synced))

    logging.info("Logged in as %s", bot.user)


@bot.tree.command(name="play", description="Play audio from a YouTube URL or search query")
@app_commands.describe(query="YouTube link or search text")
async def play(interaction: discord.Interaction, query: str) -> None:
    await interaction.response.defer()

    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("Join a voice channel first.", ephemeral=True)
        return

    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client if interaction.guild else None

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    try:
        track = await extract_track(query)
    except Exception as exc:
        logging.exception("Failed to extract track")
        await interaction.followup.send(f"Could not load track: {exc}", ephemeral=True)
        return

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    source = discord.FFmpegPCMAudio(
        track.stream_url,
        before_options=FFMPEG_BEFORE_OPTIONS,
        options=FFMPEG_OPTIONS,
    )
    voice_client.play(source)

    await interaction.followup.send(f"Now playing: [{track.title}]({track.webpage_url})")


def main() -> None:
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Create .env from .env.example.")

    bot.run(TOKEN)


if __name__ == "__main__":
    main()
