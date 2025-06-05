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
    r"\b(долбоёб|долбаеб|дебил|идиот|тупица|шлюха|шалава|мразь|сука|пидор|пидр|уёбок|еблан|чмо|гондон|гнида|козёл|петух|даун|кретин|инвалид|больной на голову|чушпан|уебан|хуесос|гавноед|ебака|недоумок|тварь|псина|сосунок|мудила|говнюк|дегенерат|попрошайка|попрошайник|пидар|хуйеглот|уебак|мрозь|шлуха|отсоси|отсосе|отсасе|соси|хуй|порно|секс|сиськи|письки|блядота|блядота|соси|тварь)\b",
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
    text_lower = text.lower()
    logging.info(f"Сообщение от @{message.from_user.username or message.from_user.id}: {text}")

    # Команда правила
    if text_lower == 'правила':
        rules_text = (
            "🗓 Правила чата:\n\n"
            "🛑 Вы можете получить бан / мут за следующие действия:\n\n"
            "1. Массовая рассылка сообщений или флуд без разрешения администрации.\n"
            "2. Попрошайничество.\n"
            "3. Оскорбление участников.\n"
            "4. Злоупотребление заглавными буквами.\n"
            "5. Отправка скримеров, стонов или распространение непристойного контента.\n"
            "6. Торговля без согласия администрации.\n"
            "7. Реклама в любом виде.\n"
            "8. Оскорбления в адрес администрации.\n"
            "9. Провокация конфликтов.\n"
            "10. Попытка раскрыть личные данные администрации.\n"
            "11. Обвинения в мошенничестве без доказательств.\n"
            "12. Оскорбления в адрес родственников участников.\n"
            "13. Жалобы на контент постов.\n"
            "14. Создание конфликтных ситуаций.\n"
            "15. Мошенничество или участие в схемах обмана.\n"
            "16. Обсуждение политических тем.\n"
            "17. Жестокий или шокирующий контент.\n"
            "18. Призывы выступать против автора.\n"
            "19. Ненужный флуд и бессмысленное общение.\n"
            "20. Шутки на тему мошенничества.\n"
            "21. Оскорбление религиозных чувств и вероисповеданий.\n"
            "22. Размещение личной информации других пользователей без их согласия.\n"
            "23. Распространение ложной или вводящей в заблуждение информации.\n"
            "24. Создание множества учетных записей для обхода блокировок.\n"
            "25. Публикация или обмен вредоносными файлами.\n\n"
            "Главный администратор - @IUVB76I, имеет право принимать меры в отношении администраторов, которые нарушили правила.\n\n"
            "Администрация оставляет за собой право принимать решения о блокировке на разный срок. Меры наказания могут варьироваться, и возможна устная просьба о корректировке поведения в первый раз."
        )
        await message.answer(rules_text)
        return

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
