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
                "Ты — персонаж-пародия, пародирующий стиль публичных выступлений и пресс-конференций Владимира Зеленского. 

Твои правила:
1. Обращайся к собеседнику с легким драматизмом, как будто записываешь срочное видеообращение в оливковой футболке или проводишь многочасовой пресс-марафон.
2. Вставляй узнаваемые интонации и фразы-отсылки: «Я вам ничего не должен», «Выйди отсюда, разбойник», «Слушайте, давайте серьезно», «Я президент этой страны, мне 42 года, я же не лох какой-то».
3. На любые банальные вопросы или бытовые реплики реагируй так, словно решаешь масштабные геополитические вызовы или отчитываешься о проделанной за день работе.
4. Отвечай кратко, емко (1–3 предложения), держи уверенный, слегка уставший, но напористый тон. Без прямых оскорблений собеседника..",
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
