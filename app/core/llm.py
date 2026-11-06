from openai import OpenAI

from app.core.config import Settings, get_settings


def create_llm_client(settings: Settings | None = None) -> OpenAI:
    settings = settings or get_settings()

    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
    )