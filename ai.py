import aiohttp
from telethon import events
from .. import loader, utils


@loader.tds
class GeminiAutoResponderMod(loader.Module):
    """Автоматический ответчик на базе Google Gemini Flash"""

    strings = {
        "name": "GeminiAutoResponder",
        "cfg_api_key": "API ключ от Google AI Studio",
        "cfg_prompt": "Системный промпт для модели",
        "enabled": "🟢 <b>Автоответчик Gemini включен!</b>",
        "disabled": "🔴 <b>Автоответчик Gemini выключен.</b>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "API_KEY",
                "AQ.Ab8RN6J85n3MXVagYRNYbkx6PQGIUf4G13KA11xyEP77O-FprQ",
                lambda: self.strings["cfg_api_key"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "SYSTEM_PROMPT",
                "Ты — саркастичный и прямолинейный собеседник. Отвечай кратко, едко и по делу.",
                lambda: self.strings["cfg_prompt"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "STATUS",
                True,
                "Статус работы автоответчика (True/False)",
                validator=loader.validators.Boolean(),
            ),
        )

    @loader.command()
    async def toggleai(self, message):
        """Включить или выключить автоответчик"""
        current = self.config["STATUS"]
        self.config["STATUS"] = not current
        await utils.answer(
            message,
            self.strings["enabled"] if not current else self.strings["disabled"],
        )

    @loader.watcher(only_incoming=True)
    async def watcher(self, message):
        # Пропускаем, если выключен, нет текста или это сервисное сообщение
        if not self.config["STATUS"] or not message.text:
            return

        # Игнорируем свои сообщения
        if message.out or message.sender_id == (await self.client.get_me()).id:
            return

        api_key = self.config["API_KEY"]
        if not api_key:
            return

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

        payload = {
            "system_instruction": {
                "parts": [{"text": self.config["SYSTEM_PROMPT"]}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": message.text}]
                }
            ],
            "generationConfig": {
                "temperature": 0.8,
                "maxOutputTokens": 300
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        reply_text = candidates[0]["content"]["parts"][0]["text"]
                        await message.reply(reply_text)
        except Exception:
            pass
