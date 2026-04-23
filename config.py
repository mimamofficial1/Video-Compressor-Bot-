import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ─── Telegram ───────────────────────────────
    API_ID       = int(os.environ.get("API_ID", 0))
    API_HASH     = os.environ.get("API_HASH", "")
    BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")

    # ─── Limits ─────────────────────────────────
    MAX_FILE_SIZE    = int(os.environ.get("MAX_FILE_SIZE", 2_000_000_000))  # 2 GB
    FFMPEG_TIMEOUT   = int(os.environ.get("FFMPEG_TIMEOUT", 1800))           # 30 min

    # ─── Database ───────────────────────────────
    DB_PATH = os.environ.get("DB_PATH", "bot_data.db")
