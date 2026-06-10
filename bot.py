from loogika.bot import LoogikaBot
from loogika.config import Settings
from loogika.logging import configure_logging


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    bot = LoogikaBot(settings)
    bot.run(settings.token, log_handler=None)


if __name__ == "__main__":
    main()
