import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_level: str = "INFO") -> None:
    """配置根日志记录器，同时输出到控制台和 logs/app.log。

    RotatingFileHandler 将每个文件限制为 10 MB，并保留最近 5 个轮转文件
    （app.log、app.log.1 到 app.log.5），避免日志目录无限增长。
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
        maxBytes=10 * 1024 * 1024,  # 每个文件最大 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    logging.basicConfig(level=level, handlers=[console, file_handler])
