import os
from openai import AsyncOpenAI

_client = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        )
    return _client


async def ask_ai(history: list[dict]) -> str:
    """history — список сообщений [{'role': 'system'|'user'|'assistant', 'content': '...'}]"""
    client = get_client()
    model = os.getenv("OPENAI_MODEL", "openai/gpt-oss-120b")
    resp = await client.chat.completions.create(model=model, messages=history)
    return resp.choices[0].message.content or "…"
