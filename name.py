import asyncio
import logging
from datetime import datetime

import pytz
from telethon.errors import FloodWaitError
from telethon.tl.functions.account import UpdateProfileRequest

from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class KyivTimeNickMod(loader.Module):
    """Автоматически меняет время в никнейме (Киевское время)"""

    strings = {
        "name": "KyivTimeNick",
        "started": "⏳ Авто-время запущено!",
        "stopped": "🛑 Авто-время остановлено.",
        "config_format": "Формат никнейма. Используй {time} для времени.",
        "config_tz": "Твой часовой пояс (например, Europe/Kyiv).",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "FORMAT",
                "fl | {time}",
                lambda: self.strings["config_format"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "TIMEZONE",
                "Europe/Kyiv",
                lambda: self.strings["config_tz"],
                validator=loader.validators.String(),
            ),
        )
        self.active = False
        self._task = None
        self._last_name = None

    async def client_ready(self, client, db):
        self.client = client

    async def on_unload(self):
        """Останавливаем фоновый процесс при выгрузке модуля"""
        self.active = False
        if self._task and not self._task.done():
            self._task.cancel()

    @loader.command()
    async def timenick(self, message):
        """Запустить или остановить смену времени в нике"""
        if self.active:
            self.active = False
            if self._task and not self._task.done():
                self._task.cancel()
            await utils.answer(message, self.strings["stopped"])
        else:
            self.active = True
            self._task = asyncio.create_task(self._time_loop())
            await utils.answer(message, self.strings["started"])

    async def _time_loop(self):
        while self.active:
            try:
                tz = pytz.timezone(self.config["TIMEZONE"])
                now = datetime.now(tz)
                current_time = now.strftime("%H:%M")
                new_name = self.config["FORMAT"].format(time=current_time)

                # Меняем только если ник действительно изменился
                if new_name != self._last_name:
                    await self.client(UpdateProfileRequest(first_name=new_name))
                    self._last_name = new_name

                # Спим ровно до начала следующей минуты + 1 секунда запаса
                seconds_to_wait = 60 - now.second + 1
                await asyncio.sleep(seconds_to_wait)

            except asyncio.CancelledError:
                break
            except FloodWaitError as e:
                logger.warning(f"Telegram FloodWait: ожидание {e.seconds} сек.")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"Ошибка обновления ника: {e}")
                await asyncio.sleep(15)
