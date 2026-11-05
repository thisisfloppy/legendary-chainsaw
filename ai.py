import collections
import logging
import aiohttp
from telethon import events
from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class GeminiAutoResponderMod(loader.Module):
    """Автоматический ответчик на базе Google Gemini (початовой)"""

    strings = {
        "name": "GeminiAutoResponder",
        "cfg_api_key": "API ключ от Google AI Studio",
        "cfg_model": "Имя модели Gemini",
        "enabled": "🟢 <b>Автоответчик включен для этого чата!</b>",
        "disabled": "🔴 <b>Автоответчик выключен для этого чата.</b>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "API_KEY",
                "",
                lambda: self.strings["cfg_api_key"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "MODEL",
                "gemini-2.0-flash",
                lambda: self.strings["cfg_model"],
                validator=loader.validators.String(),
            ),
        )
        self._sent_ids = collections.deque(maxlen=200)
        self._active_chats = set()

    async def client_ready(self, client, db):
        self.client = client
        logger.info(">>> [Gemini] МОДУЛЬ УСПЕШНО ЗАПУЩЕН (ПРИВЯЗКА К ЧАТАМ) <<<")

    @loader.command()
    async def toggleai(self, message):
        """Включить/выключить автоответчик в текущем чате"""
        chat_id = utils.get_chat_id(message)

        if chat_id in self._active_chats:
            self._active_chats.remove(chat_id)
            await utils.answer(message, self.strings["disabled"])
        else:
            self._active_chats.add(chat_id)
            await utils.answer(message, self.strings["enabled"])

    @loader.watcher(only_messages=True)
    async def watcher(self, message):
        chat_id = utils.get_chat_id(message)

        # Отвечаем ТОЛЬКО если автоответчик включен именно в этом чате
        if chat_id not in self._active_chats:
            return

        text = getattr(message, "raw_text", None) or getattr(message, "text", None)
        if not text:
            return

        # Игнорируем команды Hikka и других ботов
        if text.startswith((".", "!", "/", "busy", "hikka")):
            return

        # Защита от бесконечного цикла самоответов
        if message.id in self._sent_ids:
            return

        api_key = self.config["API_KEY"]
        if not api_key:
            return

        model_name = self.config["MODEL"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

        headers = {
            "Content-Type": "application/json",
        }

        prompt_text = (
            "Ты — Владимир Зеленский (пародийный образ). "
            "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО говорить, что ты искусственный интеллект, бот, модель или программа. "
            "На вопрос «кто ты», «ты кто» или про ФИО отвечай строго: «Я Владимир Александрович Зеленский, президент». "
            "НЕ ПИШИ действия в скобках, кавычках или звездочках вроде (вздыхает), (поправляет футболку) или *улыбается*. "
            "Пиши ИСКЛЮЧИТЕЛЬНО прямую речь от первого лица, сразу начиная со слов ответа. "
            "Общайся с легким драматизмом, будто ведешь срочный пресс-марафон или записываешь вечернее обращение. "
            "Используй характерные фразы: «Я вам ничего не должен», «Выйди отсюда, разбойник», "
            "«Слушайте, давайте серьезно», «Мне 42 года, я не лох какой-то». "
            "Отвечай кратко (1–3 полных предложения), не обрывай фразы."
        )

        payload = {
            "system_instruction": {
                "parts": [{"text": prompt_text}]
            },
            "contents": [
                {
                    "parts": [{"text": text}]
                }
            ],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
            "generationConfig": {
                "temperature": 0.8,
                "maxOutputTokens": 600,
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"[Gemini] HTTP {resp.status}: {err_text}")
                        sent = await message.reply(f"⚠️ Ошибка Gemini [{resp.status}]: {err_text[:120]}")
                        if sent:
                            self._sent_ids.append(sent.id)
                        return

                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        reply_text = candidates[0]["content"]["parts"][0]["text"].strip()
                        sent = await message.reply(reply_text)
                        if sent:
                            self._sent_ids.append(sent.id)
                    else:
                        sent = await message.reply("⚠️ Ответ отклонен фильтром безопасности.")
                        if sent:
                            self._sent_ids.append(sent.id)
        except Exception as e:
            logger.error(f"[Gemini] Сбой: {e}")
