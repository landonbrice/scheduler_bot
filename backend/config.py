from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    miniapp_url: str
    api_host: str
    api_port: int
    tasks_path: Path
    deepseek_api_key: str


def load_settings() -> Settings:
    tasks_path = os.environ.get("TASKS_PATH") or str(PROJECT_ROOT / "data" / "tasks.json")
    return Settings(
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        miniapp_url=os.environ.get("MINIAPP_URL", ""),
        api_host=os.environ.get("API_HOST", "127.0.0.1"),
        api_port=int(os.environ.get("API_PORT", "8000")),
        tasks_path=Path(tasks_path),
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
    )
