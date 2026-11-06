import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_name: str
    api_key: str
    base_url: str
    model: str
    debug: bool
    user_tz: str = "UTC"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()

    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "").strip()

    if not api_key or api_key == "your_openrouter_api_key":
        raise ValueError("AI_API_KEY is missing in .env")

    if not model or model == "your_selected_model_id":
        raise ValueError("AI_MODEL is missing in .env")

    return Settings(
        app_name=os.getenv("APP_NAME", "Personal AI Assistant"),
        api_key=api_key,
        base_url=os.getenv(
            "AI_BASE_URL",
            "https://openrouter.ai/api/v1"
        ),
        model=model,
        debug=os.getenv("DEBUG", "False").lower() == "true",
        user_tz=os.getenv("USER_TZ", "UTC").strip() or "UTC",
    )


    