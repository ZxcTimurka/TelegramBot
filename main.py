import telebot
from telebot import types
import gspread
from config import BOT_TOKEN
from oauth2client.service_account import ServiceAccountCredentials

# Telegram bot token
TOKEN = BOT_TOKEN
bot = telebot.TeleBot(TOKEN)

# oGoogle Sheets setup
# Путь к credentials.json, скачанному с Google Cloud Consle
SHEET_CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_NAME = "АЗС Отчёты"

# Настройка доступа к Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name(SHEET_CREDENTIALS_FILE, scope)
client = gspread.authorize(credentials)
sheet = client.open(SPREADSHEET_NAME).sheet1  # Открываем первый лист в таблице

# Переменные для временного хранения данных
user_data = {}

# Команда /start
@bot.message_handler(commands=['start'])
def start_command(message):
    user_data[message.chat.id] = {}
    bot.send_message(
        message.chat.id,
        "Добро пожаловать! Давайте заполним отчёт АЗС. Укажите дату отчёта (в формате ДД.ММ.ГГГГ):"
    )
    bot.register_next_step_handler(message, get_date)

# Получение даты
def get_date(message):
    user_data[message.chat.id]['date'] = message.text
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Иванова", "Петрова", "Сидорова")
    bot.send_message(
        message.chat.id,
        "Выберите оператора:",
        reply_markup=markup
    )
    bot.register_next_step_handler(message, get_operator)

# Получение оператора
def get_operator(message):
    user_data[message.chat.id]['operator'] = message.text
    bot.send_message(
        message.chat.id,
        "Укажите температуру воздуха:"
    )
    bot.register_next_step_handler(message, get_temperature)

# Получение температуры
def get_temperature(message):
    user_data[message.chat.id]['temperature'] = message.text
    bot.send_message(
        message.chat.id,
        "Добавьте комментарий (при необходимости) или отправьте \"нет\":"
    )
    bot.register_next_step_handler(message, get_comments)

# Получение комментариев
def get_comments(message):
    user_data[message.chat.id]['comments'] = message.text if message.text.lower() != "нет" else "Без комментариев"
    save_to_google_sheets(message.chat.id)
    summary = (
        f"Отчёт сформирован и отправлен в Google Sheets:\n"
        f"Дата: {user_data[message.chat.id]['date']}\n"
        f"Оператор: {user_data[message.chat.id]['operator']}\n"
        f"Температура воздуха: {user_data[message.chat.id]['temperature']}\n"
        f"Комментарий: {user_data[message.chat.id]['comments']}"
    )
    bot.send_message(message.chat.id, summary)
    bot.send_message(message.chat.id, "Спасибо! Вы можете начать новый отчёт с команды /start.")

# Функция для записи данных в Google Sheets
def save_to_google_sheets(user_id):
    data = user_data[user_id]
    sheet.append_row([
        data['date'],
        data['operator'],
        data['temperature'],
        data['comments']
    ])

# Запуск бота
bot.polling(none_stop=True)