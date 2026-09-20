import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_level: str = "INFO") -> None:
    """Configure root logger to write to both console and logs/app.log.

    RotatingFileHandler caps each file at 10 MB and keeps the last 5 rotated
    files (app.log, app.log.1 … app.log.5) so the directory never grows unbounded.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    os.makedirs("logs", exist_ok=True)

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    logging.basicConfig(level=level, handlers=[console, file_handler])
