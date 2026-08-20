import os
import json
import sqlite3
import logging
import http.client
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import Text
from aiogram.utils import executor
from aiogram.utils.exceptions import BotBlocked, UserDeactivated

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота и ID админа (для ограничения доступа к /renew)
API_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Укажите ваш Telegram ID

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- Список регионов и их точное соответствие ключам в JSON ubilling.net.ua ---
REGIONS = {
    1: {"name": "м. Київ", "key": "м. Київ"},
    2: {"name": "Київська область", "key": "Київська область"},
    3: {"name": "Вінницька область", "key": "Вінницька область"},
    4: {"name": "Волинська область", "key": "Волинська область"},
    5: {"name": "Дніпропетровська область", "key": "Дніпропетровська область"},
    6: {"name": "Донецька область", "key": "Донецька область"},
    7: {"name": "Житомирська область", "key": "Житомирська область"},
    8: {"name": "Закарпатська область", "key": "Закарпатська область"},
    9: {"name": "Запорізька область", "key": "Запорізька область"},
    10: {"name": "Івано-Франківська область", "key": "Івано-Франківська область"},
    11: {"name": "Кіровоградська область", "key": "Кіровоградська область"},
    12: {"name": "Луганська область", "key": "Луганська область"},
    13: {"name": "Львівська область", "key": "Львівська область"},
    14: {"name": "Миколаївська область", "key": "Миколаївська область"},
    15: {"name": "Одеська область", "key": "Одеська область"},
    16: {"name": "Полтавська область", "key": "Полтавська область"},
    17: {"name": "Рівненська область", "key": "Рівненська область"},
    18: {"name": "Сумська область", "key": "Сумська область"},
    19: {"name": "Тернопільська область", "key": "Тернопільська область"},
    20: {"name": "Харківська область", "key": "Харківська область"},
    21: {"name": "Херсонська область", "key": "Херсонська область"},
    22: {"name": "Хмельницька область", "key": "Хмельницька область"},
    23: {"name": "Черкаська область", "key": "Черкаська область"},
    24: {"name": "Чернівецька область", "key": "Чернівецька область"},
    25: {"name": "Чернігівська область", "key": "Чернігівська область"},
    26: {"name": "АР Крим", "key": "Автономна Республіка Крим"}
}

# --- Работа с БД (SQLite) ---
DB_FILE = "users.db"

def init_db():
    """Инициализация баз данных пользователей и статусов тревог."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Таблица пользователей и выбранных ими регионов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            region_id INTEGER NOT NULL
        )
    """)

    # Таблица для хранения текущих состояний тревоги (для сравнения при /renew)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alarm_states (
            region_id INTEGER PRIMARY KEY,
            is_active INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Заполнение таблицы начальными значениями
    for reg_id in REGIONS.keys():
        cursor.execute("""
            INSERT OR IGNORE INTO alarm_states (region_id, is_active) VALUES (?, 0)
        """, (reg_id,))

    conn.commit()
    conn.close()

def set_user_region(user_id: int, region_id: int):
    """Сохраняет или обновляет регион пользователя."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, region_id)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET region_id=excluded.region_id
    """, (user_id, region_id))
    conn.commit()
    conn.close()

def delete_user(user_id: int):
    """Удаляет пользователя из базы данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_users_by_region(region_id: int):
    """Возвращает список user_id, подписанных на указанный регион."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE region_id = ?", (region_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_user_region(user_id: int):
    """Возвращает region_id, выбранный пользователем."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT region_id FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_alarm_state(region_id: int) -> bool:
    """Получает сохраненное состояние тревоги из БД."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM alarm_states WHERE region_id = ?", (region_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False

def update_alarm_state(region_id: int, is_active: bool):
    """Обновляет состояние тревоги для региона в БД."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE alarm_states SET is_active = ? WHERE region_id = ?
    """, (1 if is_active else 0, region_id))
    conn.commit()
    conn.close()


# --- Клавиатуры ---
def build_regions_keyboard():
    """Создает Inline-клавиатуру со списком регионов."""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(
            text=f"{reg_id}. {info['name']}",
            callback_data=f"set_reg_{reg_id}"
        )
        for reg_id, info in REGIONS.items()
    ]
    keyboard.add(*buttons)
    return keyboard


# --- Оригинальный источник данных через http.client ---

def fetch_ubilling_data():
    """Получение данных о тревогах напрямую с ubilling.net.ua."""
    try:
        conn = http.client.HTTPConnection("ubilling.net.ua", timeout=10)
        conn.request("GET", "/aerialalerts/")
        res = conn.getresponse()
        data = res.read()
        conn.close()
        return json.loads(data)
    except Exception as e:
        logging.error(f"Помилка при отриманні даних з ubilling: {e}")
        return None

async def run_alarm_check_cycle():
    """
    Основной цикл проверки тревог.
    Вызывается командой /renew из client.py по cron.
    """
    response_data = fetch_ubilling_data()
    if not response_data or 'states' not in response_data:
        return "Не вдалося отримати дані з сервера ubilling."

    states = response_data['states']
    notifications_sent = 0

    # Проходим по всем подконтрольным регионам
    for reg_id, reg_info in REGIONS.items():
        state_key = reg_info['key']

        # Получаем значение alertnow из ответа сервера (True/False)
        if state_key in states:
            is_active = bool(states[state_key].get('alertnow', False))
            previous_state = get_alarm_state(reg_id)

            # Если статус тревоги изменился с момента предыдущей проверки
            if is_active != previous_state:
                update_alarm_state(reg_id, is_active)
                reg_name = reg_info['name']

                if is_active:
                    msg = f"🚨 **ПОВІТРЯНА ТРИВОГА!**\n\nУ регіоні **{reg_name}** оголошено тривогу! Прямуйте в укриття!"
                else:
                    msg = f"✅ **ВІДБIЙ ТРИВОГИ!**\n\nУ регіоні **{reg_name}** лунає відбій тривоги."

                # Отправка сообщений всем подписчикам этого региона
                users = get_users_by_region(reg_id)
                for uid in users:
                    try:
                        await bot.send_message(uid, msg, parse_mode="Markdown")
                        notifications_sent += 1
                    except (BotBlocked, UserDeactivated):
                        # Удаляем заблокировавшего бота пользователя
                        logging.info(f"Користувач {uid} заблокував бота. Видаляємо з БД.")
                        delete_user(uid)
                    except Exception as e:
                        logging.error(f"Помилка відправки користувачу {uid}: {e}")

    return f"Перевірку завершено. Відправлено сповіщень: {notifications_sent}"


# --- Хэндлеры бота ---

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Старт работы бота и выбор региона."""
    user_reg = get_user_region(message.from_user.id)

    if user_reg:
        reg_name = REGIONS[user_reg]['name']
        text = (
            f"Ви підписані на сповіщення для: **{reg_name}**.\n\n"
            f"• Перевірити статус: /check\n"
            f"• Змінити регіон: /change_city\n"
            f"• Відписатися: /unsub"
        )
        await message.answer(text)
    else:
        text = "Вітаємо! Оберіть свій регіон зі списку нижче, щоб отримувати сповіщення про повітряну тривогу:"
        await message.answer(text, reply_markup=build_regions_keyboard())

@dp.message_handler(commands=['renew'])
async def cmd_renew(message: types.Message):
    """
    Команда /renew для client.py (cron).
    Запускает одиночную проверку и рассылку.
    """
    if ADMIN_ID != 0 and message.from_user.id != ADMIN_ID:
        await message.answer("Доступ заборонено.")
        return

    status_msg = await run_alarm_check_cycle()
    await message.answer(status_msg)

@dp.message_handler(commands=['change_city'])
async def cmd_change_city(message: types.Message):
    """Команда для смены региона."""
    text = "Оберіть новий регіон зі списку:"
    await message.answer(text, reply_markup=build_regions_keyboard())

@dp.message_handler(commands=['check'])
async def cmd_check(message: types.Message):
    """Ручная проверка состояния тревоги для выбранного региона."""
    user_reg = get_user_region(message.from_user.id)

    if not user_reg:
        await message.answer("Ви ще не обрали регіон. Натисніть /start, щоб обрати свій регіон.")
        return

    reg_name = REGIONS[user_reg]['name']
    is_active = get_alarm_state(user_reg)

    if is_active:
        text = f"🚨 **Увага!** У регіоні **{reg_name}** зараз **ОГОЛОШЕНО** повітряну тривогу!"
    else:
        text = f"✅ У регіоні **{reg_name}** зараз **СПОКІЙНО** (тривоги немає)."

    await message.answer(text, parse_mode="Markdown")

@dp.message_handler(commands=['unsub'])
async def cmd_unsub(message: types.Message):
    """Отписка пользователя и удаление его данных."""
    user_id = message.from_user.id
    user_reg = get_user_region(user_id)

    if user_reg:
        delete_user(user_id)
        await message.answer(
            "❌ Ви успішно відписалися від сповіщень. Усі ваші дані видалено.\n\n"
            "Щоб відновити підписку, використайте команду /start."
        )
    else:
        await message.answer("Ви не були підписані на сповіщення.")

@dp.callback_query_handler(Text(startswith="set_reg_"))
async def process_region_selection(callback: types.CallbackQuery):
    """Обработка выбора региона из списка с отправкой нового сообщения."""
    try:
        region_id = int(callback.data.split("_")[2])
        user_id = callback.from_user.id

        # Сохраняем регион в базу данных
        set_user_region(user_id, region_id)
        region_name = REGIONS[region_id]['name']

        text = (
            f"✅ Ви успішно обрали: **{region_name}**.\n\n"
            f"Тепер ви будете отримувати сповіщення про тривоги в цьому регіоні.\n\n"
            f"Команди:\n"
            f"• Перевірити статус: /check\n"
            f"• Змінити регіон: /change_city\n"
            f"• Відписатися: /unsub"
        )

        # 1. Отправка подтверждения всплывающим плашкой/уведомлением
        await callback.answer("Регіон збережено!")

        # 2. Отправка нового обычного сообщения пользователю
        await callback.message.answer(text)

    except Exception as e:
        logging.error(f"Помилка при виборі регіону: {e}")
        await callback.answer("Помилка збереження регіону.")

# --- Запуск бота ---

async def on_startup(dp):
    init_db()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
