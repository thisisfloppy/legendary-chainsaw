import collections
import logging
import aiohttp
from telethon import events
from .. import loader, utils

logger = logging.getLogger(__name__)


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
                "AQ.Ab8RN6I5PI5Du-cyHCE3RKM8TVZ0dG4-gY5CqswDBefEItcZcg",
                lambda: self.strings["cfg_api_key"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "SYSTEM_PROMPT",
                (
                    "Ты — персонаж-пародия на публичный образ и стиль пресс-конференций Владимира Зеленского. "
                    "Общайся на русском языке с легким драматизмом, будто записываешь вечернее обращение или ведешь пресс-марафон. "
                    "Вставляй узнаваемые мемные фразы и интонации: «Я вам ничего не должен», «Выйди отсюда, разбойник», "
                    "«Слушайте, давайте серьезно», «Я президент этой страны, мне 42 года, я же не лох какой-то». "
                    "На любые оскорбления или бытовые реплики реагируй с напористой уверенностью, переводи всё на масштабные вызовы. "
                    "Отвечай кратко (1–3 предложения), держи напористый и слегка уставший тон."
                ),
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
        # Хранилище ID сообщений бота для предотвращения бесконечного цикла
        self._sent_ids = collections.deque(maxlen=200)

    @loader.command()
    async def toggleai(self, message):
        """Включить или выключить автоответчик"""
        current = self.config["STATUS"]
        self.config["STATUS"] = not current
        await utils.answer(
            message,
            self.strings["enabled"] if not current else self.strings["disabled"],
        )

    @loader.watcher()
    async def watcher(self, message):
        if not self.config["STATUS"] or not getattr(message, "text", None):
            return

        # Игнорируем команды Хикки (чтобы не скармливать команды в ИИ)
        prefix = self.get_prefix() if hasattr(self, "get_prefix") else "."
        if message.text.startswith(prefix):
            return

        # Защита от бесконечного цикла: не отвечаем на сообщения, созданные этим модулем
        if message.id in self._sent_ids:
            return

        api_key = self.config["API_KEY"]
        if not api_key:
            return

        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }

        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        payload = {
            "system_instruction": {
                "parts": [{"text": self.config["SYSTEM_PROMPT"]}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": message.text}],
                }
            ],
            "safetySettings": safety_settings,
            "generationConfig": {
                "temperature": 0.8,
                "maxOutputTokens": 300,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"[Gemini] Ошибка HTTP {resp.status}: {err_text}")
                        return

                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        reply_text = candidates[0]["content"]["parts"][0]["text"]
                        reply_msg = await message.reply(reply_text)
                        if reply_msg:
                            self._sent_ids.append(reply_msg.id)
                    else:
                        feedback = data.get("promptFeedback", {})
                        logger.warning(f"[Gemini] Ответ заблокирован: {feedback}")
        except Exception as e:
            logger.error(f"[Gemini] Сбой запроса: {e}")
