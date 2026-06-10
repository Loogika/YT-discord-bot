import logging

from loogika.music.extractor import TrackExtractor
from loogika.music.player import GuildPlayer


logger = logging.getLogger(__name__)


class PlayerManager:
    def __init__(self, extractor: TrackExtractor) -> None:
        self._extractor = extractor
        self._players: dict[int, GuildPlayer] = {}

    @property
    def extractor(self) -> TrackExtractor:
        return self._extractor

    def get(self, guild_id: int) -> GuildPlayer:
        player = self._players.get(guild_id)
        if player is None:
            player = GuildPlayer(guild_id, self._extractor)
            self._players[guild_id] = player
            logger.info(
                "Guild player created",
                extra={
                    "event": "player.created",
                    "guild_id": guild_id,
                    "player_count": len(self._players),
                },
            )
        return player

    def find(self, guild_id: int) -> GuildPlayer | None:
        return self._players.get(guild_id)

    async def remove(self, guild_id: int) -> bool:
        player = self._players.pop(guild_id, None)
        if player is None:
            return False
        disconnected = await player.close()
        logger.info(
            "Guild player removed",
            extra={
                "event": "player.removed",
                "guild_id": guild_id,
                "player_count": len(self._players),
            },
        )
        return disconnected

    async def close(self) -> None:
        players = tuple(self._players.values())
        self._players.clear()
        for player in players:
            await player.close()
