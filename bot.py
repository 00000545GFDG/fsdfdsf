import logging
import asyncio
import re
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatPermissions
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties

# ==== Настройки токена ====
API_TOKEN = '7461983178:AAEdmsfUECEst173CozI2QFBB6wI0P5Wh0Y'

# ==== Логирование ====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==== Инициализация бота ====
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==== Распознавание длительности ====
def parse_duration(text):
    text = text.strip().lower()
    units_map = {
        'минут': 'minutes', 'мин': 'minutes', 'м': 'minutes',
        'час': 'hours', 'часов': 'hours', 'ч': 'hours',
        'день': 'days', 'дня': 'days', 'дней': 'days', 'д': 'days',
        'неделя': 'weeks', 'недели': 'weeks', 'недель': 'weeks', 'н': 'weeks',
        'месяц': 'days', 'месяца': 'days', 'месяцев': 'days'
    }
    match = re.match(r'(\d+)\s*(\D+)', text)
    if not match:
        return None
    val, unit_raw = match.groups()
    val = int(val)
    for key in units_map:
        if unit_raw.startswith(key):
            unit = units_map[key]
            return timedelta(days=val * 30) if 'месяц' in key else timedelta(**{unit: val})
    return None

def build_user_link(name, user_id):
    return f'<a href="tg://user?id={user_id}">{name}</a>'

# ==== Мат-паттерны ====
INSULT_PATTERNS = [
    r"\b(?:я\s)?(?:твою\s)?мать\s?(ебал|ебу|имел)",
    r"\b(долбоёб|долбаеб|дебил|идиот|тупица|шлюха|шалава|мразь|сука|пидор|пидр|уёбок|еблан|чмо|гондон|гнида|козёл|петух|даун|кретин|инвалид|больной на голову|чушпан|уебан|хуесос|гавноед|ебака|недоумок|тварь|псина|сосунок|мудила|говнюк|дегенерат|попрошайка|попрошайник|пидар|хуйеглот|уебак|мрозь|шлуха|отсоси|отсосе|отсасе|соси|хуй|порно|секс|сиськи|письки|блядота)\b",
    r"нахуй|на хуй|иди\s+в\s+жопу|ебаный\s+рот|ебать\s+тебя|сука\s+блядь"
]

def contains_bad_words(text: str) -> bool:
    text = text.lower()
    return any(re.search(pattern, text) for pattern in INSULT_PATTERNS)

# ==== Основной обработчик ====
@dp.message(F.text)
async def handle_message(message: Message):
    chat_type = message.chat.type
    if chat_type not in ['group', 'supergroup'] or message.from_user.is_bot:
        return

    text = message.text.strip()
    logging.info(f"Сообщение от @{message.from_user.username or message.from_user.id}: {text}")

    # Мут за мат
    if contains_bad_words(text):
        until = datetime.now(timezone.utc) + timedelta(minutes=30)
        try:
            await bot.restrict_chat_member(
                message.chat.id,
                message.from_user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await message.answer(
                f"🚫 {build_user_link(message.from_user.full_name, message.from_user.id)} получил мут на 30 минут\n"
                f"💬 Причина: <i>мат</i>"
            )
        except Exception as e:
            logging.error(f"Ошибка при муте за мат: {e}")
            await message.reply("⚠️ Не удалось выдать мут. Проверь права бота.")
        return

    # Команды: мут / бан / размут
    lines = text.split('\n')
    cmd_line = lines[0].lower().strip()
    reason = lines[1].strip() if len(lines) > 1 else "Без причины"

    if cmd_line.startswith('мут'):
        if not message.reply_to_message:
            await message.reply("🔇 Ответь на сообщение. Пример:\nмут 10 минут\nспам")
            return
        target = message.reply_to_message.from_user
        duration_str = cmd_line.split(' ', 1)[1] if ' ' in cmd_line else "5 минут"
        duration = parse_duration(duration_str)
        if not duration:
            await message.reply("❗️ Неверный формат. Пример: 10 минут, 1 час, 2 дня.")
            return
        until = datetime.now(timezone.utc) + duration
        try:
            await bot.restrict_chat_member(
                message.chat.id,
                target.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await message.reply(
                f"🔇 {build_user_link(target.full_name, target.id)} замучен на {duration_str}\n"
                f"💬 Причина: {reason}"
            )
        except Exception as e:
            logging.error(f"Ошибка при муте: {e}")
            await message.reply(f"❌ Ошибка: {e}")

    elif cmd_line == 'бан':
        if not message.reply_to_message:
            await message.reply("🔨 Ответь на сообщение. Пример:\nбан\nфлуд")
            return
        target = message.reply_to_message.from_user
        try:
            await bot.ban_chat_member(message.chat.id, target.id)
            await message.reply(
                f"🔴 {build_user_link(target.full_name, target.id)} забанен\n💬 Причина: {reason}"
            )
        except Exception as e:
            logging.error(f"Ошибка при бане: {e}")
            await message.reply(f"❌ Ошибка: {e}")

    elif cmd_line == 'размут':
        if not message.reply_to_message:
            await message.reply("🔈 Ответь на сообщение. Пример:\nразмут")
            return
        target = message.reply_to_message.from_user
        try:
            await bot.restrict_chat_member(
                message.chat.id,
                target.id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_change_info=True,
                    can_invite_users=True,
                    can_pin_messages=True
                ),
                until_date=None
            )
            await message.reply(f"🔈 {build_user_link(target.full_name, target.id)} размучен.")
        except Exception as e:
            logging.error(f"Ошибка при размуте: {e}")
            await message.reply(f"❌ Ошибка: {e}")

# ==== Запуск ====
if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))
