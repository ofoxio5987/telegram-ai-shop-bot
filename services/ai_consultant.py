import httpx
import os

AI_API_KEY = os.getenv("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")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1")
AI_MODEL = os.getenv("AI_MODEL", "google/gemma-3-4b-it:free")


async def generate_ai_recommendation(user_query: str, products: list) -> str:
    """
    products = [
        {"name": "...", "price": 1000, "category": "..."},
        ...
    ]
    """

    if not AI_API_KEY:
        return None  # fallback — нет AI

    # формируем список товаров
    product_list = "\n".join([
        f"{i+1}. {p['name']} — {p['price']} тг — категория: {p['category']}"
        for i, p in enumerate(products[:10])
    ])

    prompt = f"""
Ты консультант интернет-магазина.

Пользователь запросил:
"{user_query}"

Вот доступные товары:
{product_list}

Выбери 2-3 лучших варианта.
Объясни кратко, почему они подходят.

ВАЖНО:
- Не придумывай товары
- Пиши кратко
- На русском языке
"""

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": "Ты помощник магазина."},
                        {"role": "user", "content": prompt}
                    ]
                }
            )

        data = response.json()
        return data["choices"][0]["message"]["content"]

    except Exception:
        return None