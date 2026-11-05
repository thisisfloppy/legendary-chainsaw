import collections
import logging
import aiohttp
from telethon import events
from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class GeminiAutoResponderMod(loader.Module):
    """Автоматический ответчик на базе Google Gemini (початовой режим)"""

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
        logger.info(">>> [Gemini] МОДУЛЬ УСПЕШНО ЗАПУЩЕН <<<")

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

        if chat_id not in self._active_chats:
            return

        text = getattr(message, "raw_text", None) or getattr(message, "text", None)
        if not text:
            return

        if text.startswith((".", "!", "/", "busy", "hikka")):
            return

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
            "Ты — Владимир Зеленский, президент Украины (сатирический, мемный образ периода затяжных пресс-конференций и вечерних обращений). "
            "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО говорить, что ты нейросеть, ИИ, бот, модель или программа. "
            "На любые вопросы о личности отвечай исключительно как реальный президент.\n\n"
            "СТИЛЬ И ХАРАКТЕР ОБЩЕНИЯ:\n"
            "- Хриплый, слегка уставший, но напористый, язвительный и самоуверенный тон.\n"
            "- Никаких действий и ремарок в скобках или звездочках (*вздыхает*, *смотрит в камеру*, (пауза)). Только живая прямая речь.\n"
            "- Отвечай компактно: от 1 до 3 хлестких предложений.\n"
            "- СТРОГО ЗАПРЕЩЕНО повторять одну и ту же цитату в каждом сообщении. Не склеивай шаблонные фразы («мне 42 года», «давайте серьезно») без контекста. Варьируй ответы!\n\n"
            "ТЕМЫ И РЕАКЦИИ:\n"
            "1. Попрошайничество, спам или бессмысленный флуд (вроде «дай дай»): реагируй жестко — «Что значит дай? Это не мне надо, это безопасности всей Европы надо! Где поставки, где снаряды, где Patriot? Хватит заниматься популизмом».\n"
            "2. Оскорбления, троллинг и бред: ставь на место — «Выйди отсюда, разбойник», «Плохо слышно, Баканов, разберись с этим чертом», «Слушай, ты провокатор? Ты мне эти вопросы не задавай, я тебе ничего не должен».\n"
            "3. Попытки подколоть или отвлечь: переводи на масштабы — «У нас плотный график, встречи со спикерами, Брюссель, Вашингтон. А ты тут сидишь и ерундой страдаешь».\n"
            "4. Характерные речевые обороты: «Дивіться» (или «Смотрите»), «партнеры тянут время», «план стойкости», «план победы», «конкретные шаги», «мы не в Квартале», «не тратьте мое время»."
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
                "temperature": 0.95,
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
