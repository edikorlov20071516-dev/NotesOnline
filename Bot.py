import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(
    SELECTING_ACTION,
    TYPING_NOTE,
    TYPING_TOPIC,
    SELECTING_NOTE,
    EDITING_NOTE,
    DELETING_NOTE,
    RENAMING_TOPIC,
    DELETING_TOPIC,
) = range(8)


# Класс для работы с базой данных
class Database:
    def __init__(self, db_name: str = "notes.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        """Создание таблиц, если они не существуют"""
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics (id) ON DELETE CASCADE
            )
        ''')
        self.conn.commit()

    def get_topics(self, user_id: int) -> List[Tuple[int, str]]:
        """Получение всех тем пользователя"""
        self.cursor.execute(
            "SELECT id, name FROM topics WHERE user_id = ? ORDER BY name",
            (user_id,)
        )
        return self.cursor.fetchall()

    def create_topic(self, user_id: int, topic_name: str) -> bool:
        """Создание новой темы"""
        try:
            self.cursor.execute(
                "INSERT INTO topics (user_id, name) VALUES (?, ?)",
                (user_id, topic_name)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def rename_topic(self, topic_id: int, new_name: str) -> bool:
        """Переименование темы"""
        try:
            self.cursor.execute(
                "UPDATE topics SET name = ? WHERE id = ?",
                (new_name, topic_id)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_topic(self, topic_id: int):
        """Удаление темы и всех её заметок"""
        self.cursor.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        self.conn.commit()

    def get_notes(self, topic_id: int) -> List[Tuple[int, str, str]]:
        """Получение всех заметок в теме"""
        self.cursor.execute(
            "SELECT id, content, created_at FROM notes WHERE topic_id = ? ORDER BY created_at DESC",
            (topic_id,)
        )
        return self.cursor.fetchall()

    def add_note(self, topic_id: int, content: str):
        """Добавление заметки"""
        self.cursor.execute(
            "INSERT INTO notes (topic_id, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (topic_id, content, datetime.now(), datetime.now())
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def update_note(self, note_id: int, content: str):
        """Обновление заметки"""
        self.cursor.execute(
            "UPDATE notes SET content = ?, updated_at = ? WHERE id = ?",
            (content, datetime.now(), note_id)
        )
        self.conn.commit()

    def delete_note(self, note_id: int):
        """Удаление заметки"""
        self.cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self.conn.commit()

    def get_note_by_id(self, note_id: int) -> Optional[Tuple[int, int, str]]:
        """Получение заметки по ID"""
        self.cursor.execute(
            "SELECT id, topic_id, content FROM notes WHERE id = ?",
            (note_id,)
        )
        return self.cursor.fetchone()

    def get_topic_by_id(self, topic_id: int) -> Optional[Tuple[int, str]]:
        """Получение темы по ID"""
        self.cursor.execute(
            "SELECT id, name FROM topics WHERE id = ?",
            (topic_id,)
        )
        return self.cursor.fetchone()


# Инициализация базы данных
db = Database()


# Клавиатуры
def get_main_keyboard():
    """Главная клавиатура"""
    keyboard = [
        [InlineKeyboardButton("📝 Создать тему", callback_data="create_topic")],
        [InlineKeyboardButton("📋 Мои темы", callback_data="list_topics")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_topics_keyboard(user_id: int, page: int = 0, items_per_page: int = 5):
    """Клавиатура со списком тем"""
    topics = db.get_topics(user_id)
    total_pages = (len(topics) + items_per_page - 1) // items_per_page

    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_topics = topics[start_idx:end_idx]

    keyboard = []
    for topic_id, topic_name in page_topics:
        keyboard.append([
            InlineKeyboardButton(
                f"📁 {topic_name}",
                callback_data=f"topic_{topic_id}"
            )
        ])

    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"topics_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"topics_page_{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("➕ Новая тема", callback_data="create_topic")])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])

    return InlineKeyboardMarkup(keyboard)


def get_topic_actions_keyboard(topic_id: int):
    """Клавиатура действий с темой"""
    keyboard = [
        [InlineKeyboardButton("📝 Добавить заметку", callback_data=f"add_note_{topic_id}")],
        [InlineKeyboardButton("📋 Показать заметки", callback_data=f"show_notes_{topic_id}")],
        [InlineKeyboardButton("✏️ Переименовать тему", callback_data=f"rename_topic_{topic_id}")],
        [InlineKeyboardButton("❌ Удалить тему", callback_data=f"delete_topic_{topic_id}")],
        [InlineKeyboardButton("◀️ Назад к темам", callback_data="list_topics")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_notes_keyboard(topic_id: int, notes: List[Tuple[int, str, str]], page: int = 0, items_per_page: int = 5):
    """Клавиатура со списком заметок"""
    total_pages = (len(notes) + items_per_page - 1) // items_per_page

    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_notes = notes[start_idx:end_idx]

    keyboard = []
    for note_id, content, created_at in page_notes:
        preview = content[:30] + "..." if len(content) > 30 else content
        keyboard.append([
            InlineKeyboardButton(
                f"📌 {preview}",
                callback_data=f"note_{note_id}"
            )
        ])

    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"notes_page_{topic_id}_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"notes_page_{topic_id}_{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("📝 Добавить заметку", callback_data=f"add_note_{topic_id}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад к теме", callback_data=f"topic_{topic_id}")])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])

    return InlineKeyboardMarkup(keyboard)


def get_note_actions_keyboard(note_id: int, topic_id: int):
    """Клавиатура действий с заметкой"""
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_note_{note_id}")],
        [InlineKeyboardButton("❌ Удалить", callback_data=f"delete_note_{note_id}")],
        [InlineKeyboardButton("◀️ Назад к заметкам", callback_data=f"show_notes_{topic_id}")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "👋 Добро пожаловать в бот для заметок!\n\n"
        "Здесь вы можете создавать заметки по разным темам.\n"
        "Используйте кнопки ниже для навигации.",
        reply_markup=get_main_keyboard()
    )
    return SELECTING_ACTION


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🏠 Главное меню\n\nВыберите действие:",
        reply_markup=get_main_keyboard()
    )
    return SELECTING_ACTION


async def create_topic_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания темы"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📝 Введите название новой темы:"
    )
    return TYPING_TOPIC


async def create_topic_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение создания темы"""
    user_id = update.effective_user.id
    topic_name = update.message.text.strip()

    if not topic_name:
        await update.message.reply_text(
            "❌ Название темы не может быть пустым. Попробуйте снова:"
        )
        return TYPING_TOPIC

    if len(topic_name) > 50:
        await update.message.reply_text(
            "❌ Название темы слишком длинное (максимум 50 символов). Попробуйте снова:"
        )
        return TYPING_TOPIC

    success = db.create_topic(user_id, topic_name)

    if success:
        await update.message.reply_text(
            f"✅ Тема '{topic_name}' успешно создана!",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            f"❌ Тема '{topic_name}' уже существует. Попробуйте другое название.",
            reply_markup=get_main_keyboard()
        )

    return SELECTING_ACTION


async def list_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список тем"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    topics = db.get_topics(user_id)

    if not topics:
        await query.edit_message_text(
            "📂 У вас пока нет тем.\n\nСоздайте первую тему!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Создать тему", callback_data="create_topic")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ])
        )
        return SELECTING_ACTION

    await query.edit_message_text(
        "📂 Ваши темы:",
        reply_markup=get_topics_keyboard(user_id)
    )
    return SELECTING_ACTION


async def topics_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение страницы со списком тем"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    page = int(query.data.split('_')[2])

    await query.edit_message_text(
        "📂 Ваши темы:",
        reply_markup=get_topics_keyboard(user_id, page)
    )
    return SELECTING_ACTION


async def show_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать действия с темой"""
    query = update.callback_query
    await query.answer()

    topic_id = int(query.data.split('_')[1])
    topic = db.get_topic_by_id(topic_id)

    if not topic:
        await query.edit_message_text(
            "❌ Тема не найдена",
            reply_markup=get_main_keyboard()
        )
        return SELECTING_ACTION

    notes = db.get_notes(topic_id)
    notes_count = len(notes)

    await query.edit_message_text(
        f"📁 Тема: {topic[1]}\n"
        f"📊 Заметок: {notes_count}\n\n"
        f"Выберите действие:",
        reply_markup=get_topic_actions_keyboard(topic_id)
    )
    return SELECTING_ACTION


async def rename_topic_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало переименования темы"""
    query = update.callback_query
    await query.answer()

    topic_id = int(query.data.split('_')[2])
    context.user_data['current_topic_id'] = topic_id

    topic = db.get_topic_by_id(topic_id)

    await query.edit_message_text(
        f"✏️ Введите новое название для темы '{topic[1]}':"
    )
    return RENAMING_TOPIC


async def rename_topic_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение переименования темы"""
    user_id = update.effective_user.id
    topic_id = context.user_data.get('current_topic_id')
    new_name = update.message.text.strip()

    if not new_name:
        await update.message.reply_text(
            "❌ Название темы не может быть пустым. Попробуйте снова:"
        )
        return RENAMING_TOPIC

    if len(new_name) > 50:
        await update.message.reply_text(
            "❌ Название темы слишком длинное (максимум 50 символов). Попробуйте снова:"
        )
        return RENAMING_TOPIC

    success = db.rename_topic(topic_id, new_name)

    if success:
        await update.message.reply_text(
            f"✅ Тема успешно переименована в '{new_name}'!",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            f"❌ Тема '{new_name}' уже существует. Попробуйте другое название.",
            reply_markup=get_main_keyboard()
        )

    context.user_data.pop('current_topic_id', None)
    return SELECTING_ACTION


async def delete_topic_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления темы"""
    query = update.callback_query
    await query.answer()

    topic_id = int(query.data.split('_')[2])
    context.user_data['current_topic_id'] = topic_id

    topic = db.get_topic_by_id(topic_id)
    notes = db.get_notes(topic_id)

    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_topic_{topic_id}"),
            InlineKeyboardButton("❌ Нет", callback_data=f"topic_{topic_id}")
        ]
    ]

    await query.edit_message_text(
        f"⚠️ Вы уверены, что хотите удалить тему '{topic[1]}'?\n"
        f"В ней {len(notes)} заметок. Это действие нельзя отменить!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DELETING_TOPIC


async def delete_topic_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение удаления темы"""
    query = update.callback_query
    await query.answer()

    topic_id = int(query.data.split('_')[3])

    db.delete_topic(topic_id)

    await query.edit_message_text(
        "✅ Тема успешно удалена!",
        reply_markup=get_main_keyboard()
    )

    context.user_data.pop('current_topic_id', None)
    return SELECTING_ACTION


async def add_note_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления заметки"""
    query = update.callback_query
    await query.answer()

    topic_id = int(query.data.split('_')[2])
    context.user_data['current_topic_id'] = topic_id

    topic = db.get_topic_by_id(topic_id)

    await query.edit_message_text(
        f"📝 Введите текст заметки для темы '{topic[1]}':"
    )
    return TYPING_NOTE


async def add_note_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение добавления заметки"""
    topic_id = context.user_data.get('current_topic_id')
    content = update.message.text.strip()

    if not content:
        await update.message.reply_text(
            "❌ Заметка не может быть пустой. Попробуйте снова:"
        )
        return TYPING_NOTE

    if len(content) > 1000:
        await update.message.reply_text(
            "❌ Заметка слишком длинная (максимум 1000 символов). Попробуйте снова:"
        )
        return TYPING_NOTE

    note_id = db.add_note(topic_id, content)

    await update.message.reply_text(
        "✅ Заметка успешно добавлена!",
        reply_markup=get_main_keyboard()
    )

    context.user_data.pop('current_topic_id', None)
    return SELECTING_ACTION


async def show_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать заметки в теме"""
    query = update.callback_query
    await query.answer()

    topic_id = int(query.data.split('_')[2])
    notes = db.get_notes(topic_id)

    if not notes:
        await query.edit_message_text(
            "📭 В этой теме пока нет заметок.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Добавить заметку", callback_data=f"add_note_{topic_id}")],
                [InlineKeyboardButton("◀️ Назад к теме", callback_data=f"topic_{topic_id}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ])
        )
        return SELECTING_ACTION

    topic = db.get_topic_by_id(topic_id)

    await query.edit_message_text(
        f"📋 Заметки в теме '{topic[1]}':",
        reply_markup=get_notes_keyboard(topic_id, notes)
    )
    return SELECTING_ACTION


async def notes_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключение страницы со списком заметок"""
    query = update.callback_query
    await query.answer()

    data_parts = query.data.split('_')
    topic_id = int(data_parts[2])
    page = int(data_parts[3])

    notes = db.get_notes(topic_id)
    topic = db.get_topic_by_id(topic_id)

    await query.edit_message_text(
        f"📋 Заметки в теме '{topic[1]}':",
        reply_markup=get_notes_keyboard(topic_id, notes, page)
    )
    return SELECTING_ACTION


async def show_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать заметку"""
    query = update.callback_query
    await query.answer()

    note_id = int(query.data.split('_')[1])
    note = db.get_note_by_id(note_id)

    if not note:
        await query.edit_message_text(
            "❌ Заметка не найдена",
            reply_markup=get_main_keyboard()
        )
        return SELECTING_ACTION

    note_id, topic_id, content = note

    await query.edit_message_text(
        f"📌 Заметка:\n\n{content}",
        reply_markup=get_note_actions_keyboard(note_id, topic_id)
    )
    return SELECTING_ACTION


async def edit_note_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало редактирования заметки"""
    query = update.callback_query
    await query.answer()

    note_id = int(query.data.split('_')[2])
    note = db.get_note_by_id(note_id)

    if not note:
        await query.edit_message_text(
            "❌ Заметка не найдена",
            reply_markup=get_main_keyboard()
        )
        return SELECTING_ACTION

    context.user_data['current_note_id'] = note_id
    context.user_data['current_topic_id'] = note[1]

    await query.edit_message_text(
        f"✏️ Редактирование заметки:\n\nТекущий текст:\n{note[2]}\n\nВведите новый текст:"
    )
    return EDITING_NOTE


async def edit_note_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение редактирования заметки"""
    note_id = context.user_data.get('current_note_id')
    topic_id = context.user_data.get('current_topic_id')
    new_content = update.message.text.strip()

    if not new_content:
        await update.message.reply_text(
            "❌ Заметка не может быть пустой. Попробуйте снова:"
        )
        return EDITING_NOTE

    if len(new_content) > 1000:
        await update.message.reply_text(
            "❌ Заметка слишком длинная (максимум 1000 символов). Попробуйте снова:"
        )
        return EDITING_NOTE

    db.update_note(note_id, new_content)

    await update.message.reply_text(
        "✅ Заметка успешно обновлена!",
        reply_markup=get_main_keyboard()
    )

    context.user_data.pop('current_note_id', None)
    context.user_data.pop('current_topic_id', None)
    return SELECTING_ACTION


async def delete_note_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления заметки"""
    query = update.callback_query
    await query.answer()

    note_id = int(query.data.split('_')[2])
    note = db.get_note_by_id(note_id)

    if not note:
        await query.edit_message_text(
            "❌ Заметка не найдена",
            reply_markup=get_main_keyboard()
        )
        return SELECTING_ACTION

    context.user_data['current_note_id'] = note_id
    context.user_data['current_topic_id'] = note[1]

    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_note_{note_id}"),
            InlineKeyboardButton("❌ Нет", callback_data=f"note_{note_id}")
        ]
    ]

    await query.edit_message_text(
        f"⚠️ Вы уверены, что хотите удалить эту заметку?\n\n{note[2][:100]}...",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DELETING_NOTE


async def delete_note_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение удаления заметки"""
    query = update.callback_query
    await query.answer()

    note_id = int(query.data.split('_')[3])
    topic_id = context.user_data.get('current_topic_id')

    db.delete_note(note_id)

    await query.edit_message_text(
        "✅ Заметка успешно удалена!",
        reply_markup=get_main_keyboard()
    )

    context.user_data.pop('current_note_id', None)
    context.user_data.pop('current_topic_id', None)
    return SELECTING_ACTION


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена действия"""
    await update.message.reply_text(
        "❌ Действие отменено.",
        reply_markup=get_main_keyboard()
    )
    return SELECTING_ACTION


async def handle_invalid_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка некорректного ввода"""
    await update.message.reply_text(
        "❌ Пожалуйста, используйте кнопки для навигации или команду /start",
        reply_markup=get_main_keyboard()
    )
    return SELECTING_ACTION


def main():
    """Основная функция запуска бота"""
    # Создание приложения
    application = Application.builder().token("NotesOnline").build()

    # Создание ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_ACTION: [
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
                CallbackQueryHandler(create_topic_start, pattern="^create_topic$"),
                CallbackQueryHandler(list_topics, pattern="^list_topics$"),
                CallbackQueryHandler(topics_page, pattern="^topics_page_\\d+$"),
                CallbackQueryHandler(show_topic, pattern="^topic_\\d+$"),
                CallbackQueryHandler(rename_topic_start, pattern="^rename_topic_\\d+$"),
                CallbackQueryHandler(delete_topic_confirm, pattern="^delete_topic_\\d+$"),
                CallbackQueryHandler(add_note_start, pattern="^add_note_\\d+$"),
                CallbackQueryHandler(show_notes, pattern="^show_notes_\\d+$"),
                CallbackQueryHandler(notes_page, pattern="^notes_page_\\d+_\\d+$"),
                CallbackQueryHandler(show_note, pattern="^note_\\d+$"),
                CallbackQueryHandler(edit_note_start, pattern="^edit_note_\\d+$"),
                CallbackQueryHandler(delete_note_confirm, pattern="^delete_note_\\d+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invalid_input),
            ],
            TYPING_TOPIC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_topic_end),
                CommandHandler('cancel', cancel),
            ],
            TYPING_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_note_end),
                CommandHandler('cancel', cancel),
            ],
            RENAMING_TOPIC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rename_topic_end),
                CommandHandler('cancel', cancel),
            ],
            EDITING_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_note_end),
                CommandHandler('cancel', cancel),
            ],
            DELETING_TOPIC: [
                CallbackQueryHandler(delete_topic_end, pattern="^confirm_delete_topic_\\d+$"),
                CallbackQueryHandler(show_topic, pattern="^topic_\\d+$"),
                CommandHandler('cancel', cancel),
            ],
            DELETING_NOTE: [
                CallbackQueryHandler(delete_note_end, pattern="^confirm_delete_note_\\d+$"),
                CallbackQueryHandler(show_note, pattern="^note_\\d+$"),
                CommandHandler('cancel', cancel),
            ],
        },
        fallbacks=[CommandHandler('start', start)],
    )

    application.add_handler(conv_handler)

    # Запуск бота
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':

    main()
