import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import config
from collections import defaultdict



# Конфигурация бота
API_TOKEN = config.API_TOKEN
CHANNEL_ID = config.CHANNEL_ID  # Канал для проверки подписки
ADMIN_USER_ID = 750485827  # Telegram ID пользователя, который может загружать фильмы

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# FSM Состояния
class UserStates(StatesGroup):
    waiting_for_subscription = State()
    main_menu = State()

# Подключение к базе данных
conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# Создание таблицы, если её ещё нет
cursor.execute("""
CREATE TABLE IF NOT EXISTS Movies (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    Title TEXT UNIQUE NOT NULL,
    file_id TEXT NOT NULL
)
""")
conn.commit()

last_bot_messages = defaultdict(lambda: None)  # Хранит ID последних сообщений бота по chat_id

async def delete_previous_message(chat_id: int, bot_message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=bot_message_id)
    except Exception:
        pass  # Игнорируем ошибки, если сообщение уже удалено или недоступно



# Команда /start
@router.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    subscribe_button = InlineKeyboardButton(text="Подписался", callback_data="check_subscription")
    markup = InlineKeyboardMarkup(inline_keyboard=[[subscribe_button]])

    await message.answer(
        "Для использования бота подпишитесь на спонсорский канал @FlLMFIX и нажмите 'Подписался'.",
        reply_markup=markup
    )
    await state.set_state(UserStates.waiting_for_subscription)

# Проверка подписки
@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    member = await bot.get_chat_member(CHANNEL_ID, user_id)
    if member.status in ["member", "administrator", "creator"]:
        await callback.message.edit_text("Спасибо за подписку! Добро пожаловать в меню.")
        await show_movies_menu(callback.message)
        await state.set_state(UserStates.main_menu)
    else:
        await callback.answer("Пожалуйста, подпишитесь на канал и повторите попытку.", show_alert=True)


# Показ меню с фильмами
async def show_movies_menu(message: Message):
    # Получаем список фильмов из базы данных
    cursor.execute("SELECT Title FROM Movies")
    movies = cursor.fetchall()

    # Проверяем, есть ли фильмы
    if not movies:
        await message.answer("В данный момент нет доступных фильмов.")
        return

    # Создаем клавиатуру с названиями фильмов
    inline_keyboard = [
        [InlineKeyboardButton(text=movie[0], callback_data=f"movie_{movie[0]}")]
        for movie in movies
    ]

    # Передаем список списков кнопок в InlineKeyboardMarkup
    markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    await message.answer("Выберите фильм:", reply_markup=markup)



# Обработка выбора фильма
@router.callback_query(F.data.startswith("movie_"))
async def send_movie(callback: CallbackQuery):
    # Извлекаем название фильма из callback_data
    movie_title = callback.data.replace("movie_", "")

    # Ищем файл в базе данных
    cursor.execute("SELECT file_id FROM Movies WHERE Title = ?", (movie_title,))
    result = cursor.fetchone()

    if result:
        file_id = result[0]
        await bot.send_video(chat_id=callback.message.chat.id, video=file_id, caption=f"Фильм: {movie_title}")
    else:
        await callback.message.answer("Фильм не найден.")


# Загрузка фильмов (только для администратора)
@router.message(F.video)
async def save_video(message: Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.reply("У вас нет прав для загрузки фильмов.")
        return

    file_id = message.video.file_id
    title = message.caption or "Без названия"

    try:
        cursor.execute("INSERT INTO Movies (Title, file_id) VALUES (?, ?)", (title, file_id))
        conn.commit()
        await message.reply(f"Фильм '{title}' успешно сохранён!")
    except sqlite3.IntegrityError:
        await message.reply("Фильм с таким названием уже существует.")


# Обработка всех сообщений, на которые нет обработчиков
@router.message()
async def unknown_message_handler(message: Message):
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass  # Игнорируем ошибки удаления

    # Проверяем, было ли отправлено предыдущее сообщение
    chat_id = message.chat.id
    last_message_id = last_bot_messages[chat_id]

    # Если есть предыдущее сообщение, удаляем его
    if last_message_id:
        await delete_previous_message(chat_id, last_message_id)

    # Отправляем новое сообщение
    bot_message = await message.answer(
        "Команда не распознана. Введите /start для начала работы с ботом."
    )

    # Сохраняем ID нового сообщения
    last_bot_messages[chat_id] = bot_message.message_id



# Основной запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
