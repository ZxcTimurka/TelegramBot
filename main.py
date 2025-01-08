import telebot
from telebot.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, InlineKeyboardButton, KeyboardButton
from datetime import datetime, timedelta
import gspread
from config import BOT_TOKEN
from oauth2client.service_account import ServiceAccountCredentials

# Telegram bot token
TOKEN = BOT_TOKEN
bot = telebot.TeleBot(TOKEN)

# Google Sheets setup
SHEET_CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_NAME = "АЗС Отчёты"

# Настройка доступа к Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name(SHEET_CREDENTIALS_FILE, scope)
client = gspread.authorize(credentials)
sheet = client.open(SPREADSHEET_NAME).sheet1  # Открываем первый лист в таблице

# Переменные для временного хранения данных
user_data = {}
current_index = 0
debt = False

def generate_calendar(year, month):
    markup = InlineKeyboardMarkup()
    # Название месяца и навигация
    row = [
        InlineKeyboardButton("⬅️", callback_data=f"prev_month_{year}_{month}"),
        InlineKeyboardButton(f"{datetime(year, month, 1):%B %Y}", callback_data="ignore"),
        InlineKeyboardButton("➡️", callback_data=f"next_month_{year}_{month}")
    ]
    markup.row(*row)
    
    # Дни недели
    days = ["", "", "", "", "", "", ""]
    markup.row(*[InlineKeyboardButton(day, callback_data="ignore") for day in days])
    
    # Дни месяца
    first_day = datetime(year, month, 1)
    last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    calendar_days = ["" for _ in range(first_day.weekday())]  # Пустые кнопки до первого дня месяца
    calendar_days += [str(day) for day in range(1, last_day.day + 1)]
    
    for week in range(0, len(calendar_days), 7):
        row = [
            InlineKeyboardButton(day, callback_data=f"select_date_{year}_{month}_{day}")
            if day else InlineKeyboardButton(" ", callback_data="ignore")
            for day in calendar_days[week:week + 7]
        ]
        markup.row(*row)
    return markup

# Команда /start
@bot.message_handler(commands=['start'])
def start_command(message):
    user_data[message.chat.id] = {
        'state': 'start'  # Possible states: 'start', 'creating_report', 'correcting_data'
    }
    user_data[message.chat.id] = {}
    keyboard = InlineKeyboardMarkup()
    button_create = InlineKeyboardButton(text="Создать отчёт", callback_data="create_report")
    keyboard.add(button_create)
    bot.send_message(
        message.chat.id,
        "Бот АЗС приветствует вас!",
        reply_markup=keyboard
    )


@bot.message_handler(commands=['stop'])
def stop_command(message):
    chat_id = message.chat.id
    # Убираем пользователя из ожидаемого состояния
    bot.clear_step_handler_by_chat_id(chat_id)
    # Очищаем временные данные пользователя
    user_data.pop(chat_id, None)
    bot.send_message(chat_id, "Заполнение отчета прервано.")

@bot.message_handler(func=lambda message: message.text.startswith('/'))
def handle_commands(message):
    if message.text == '/stop':
        stop_command(message)  # Вызываем обработчик команды /stop
    else:
        bot.send_message(message.chat.id, "Неизвестная команда. Попробуйте /stop или /start.")

@bot.callback_query_handler(func=lambda call: call.data == "create_report")
def create_report(call):
    user_data[call.message.chat.id]['state'] = 'creating_report'
    bot.delete_message(call.message.chat.id, call.message.message_id)
    now = datetime.now()
    markup = generate_calendar(now.year, now.month)
    bot.send_message(call.message.chat.id, "Выберите дату отчета", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_date_") or call.data.startswith("prev_month_") or call.data.startswith("next_month_") or call.data == "ignore")
def callback_query(call):
    data = call.data.split("_")
    
    if data[0] == "ignore":
        bot.answer_callback_query(call.id)  # Ничего не делаем
    
    if data[0] == "prev" or data[0] == "next":
        year, month = int(data[2]), int(data[3])
        if data[0] == "prev":
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        elif data[0] == "next":
            month += 1
            if month == 13:
                month = 1
                year += 1
        # Обновляем календарь
        markup = generate_calendar(year, month)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    if data[0] == "select":
        year, month, day = int(data[2]), int(data[3]), int(data[4])
        selected_date = datetime(year, month, day).strftime("%d.%m.%Y")
        user_data[call.message.chat.id]['date'] = selected_date
        if user_data[call.message.chat.id].get('state') == 'correcting_data':
            bot.delete_message(call.message.chat.id, call.message.message_id)
            show_summary(call.message.chat.id)
        else:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            global operator1, operator2, operator3
            operator1 = 'Оператор 1'
            operator2 = 'Оператор 2'
            operator3 = 'Оператор 3'
            markup.add(operator1, operator2, operator3, "Другой")
            bot.send_message(call.message.chat.id, f"Вы выбрали дату: {selected_date}\n\nУкажите оператора:", reply_markup=markup)
            bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda message: message.text in ["Оператор 1", "Оператор 2", "Оператор 3", "Другой"])
def handle_operator_choice(message):
    if message.text == "Другой":
        bot.send_message(message.chat.id, "Введите имя оператора:")
        bot.register_next_step_handler(message, get_operator)
    else:
        user_data[message.chat.id]['operator'] = message.text
        bot.send_message(message.chat.id, "Укажите температуру воздуха на дату отчёта:")
        bot.register_next_step_handler(message, get_temperature)

# Получение оператора
def get_operator(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isalpha():
        bot.send_message(message.chat.id, "Пожалуйста, введите корректное имя оператора:")
        bot.register_next_step_handler(message, get_operator)
        return
    user_data[message.chat.id]['operator'] = message.text
    bot.send_message(message.chat.id, "Укажите температуру воздуха:")
    bot.register_next_step_handler(message, get_temperature)

# Получение температуры
def get_temperature(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    try:
        temperature = float(message.text.replace(",", "."))
    except ValueError:
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение температуры:")
        bot.register_next_step_handler(message, get_temperature)
        return
    user_data[message.chat.id]['temperature'] = message.text
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Добавить Комментарии", "Нет Комментариев")
    bot.send_message(message.chat.id, "Добавить комментарии по отчетному дню (прокачка, взлив, и т.д.):", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ["Добавить Комментарии", "Нет Комментариев"])
def handle_comments_choice(message):
    if message.text == "Добавить Комментарии":
        bot.send_message(message.chat.id, "Введите комментарии:")
        bot.register_next_step_handler(message, get_comments)
    elif message.text == 'Нет Комментариев':
        user_data[message.chat.id]['comments'] = "Без комментариев"
        show_summary(message.chat.id)

# Получение комментариев
def get_comments(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    user_data[message.chat.id]['comments'] = message.text
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Всё верно, сохранить данные", "Нужно изменить данные")
    summary = (
        f"Проверьте данные для сохраниения в отчет 1/3:\n"
        f"Дата: {user_data[message.chat.id]['date']}\n"
        f"Оператор: {user_data[message.chat.id]['operator']}\n"
        f"Температура воздуха: {user_data[message.chat.id]['temperature']}\n"
        f"Комментарий: {user_data[message.chat.id]['comments']}"
    )
    bot.send_message(message.chat.id, summary, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ["Всё верно, сохранить данные", "Нужно изменить данные"])
def handle_data_confirmation(message):
    if message.text == "Всё верно, сохранить данные":
        next_block2(message) # Pass the message object, not just the chat ID
    else:
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Дата", "Оператор", "Температура", "Комментарий", "Ничего менять не нужно")
        bot.send_message(message.chat.id, "Какие данные необходимо исправить?", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ["Дата", "Оператор", "Температура", "Комментарий", "Ничего менять не нужно"])
def handle_data_correction(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if message.text == "Ничего менять не нужно":
        next_block2(message) # Pass the message object, not just the chat ID
    
    if message.text == "Дата":
        user_data[message.chat.id]['state'] = 'correcting_data'
        now = datetime.now()
        markup = generate_calendar(now.year, now.month)
        bot.send_message(message.chat.id, "Выберите новую дату отчета", reply_markup=markup)
    
    elif message.text == "Оператор":
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(operator1, operator2, operator3, "Другой")
        bot.send_message(message.chat.id, "Укажите нового оператора:", reply_markup=markup)
        bot.register_next_step_handler(message, update_operator)
    
    elif message.text == "Температура":
        bot.send_message(message.chat.id, "Укажите новую температуру воздуха:")
        bot.register_next_step_handler(message, update_temperature)
    
    elif message.text == "Комментарий":
        bot.send_message(message.chat.id, "Введите новые комментарии:")
        bot.register_next_step_handler(message, update_comments)

def update_operator(message):
    if message.text == "Другой":
        bot.send_message(message.chat.id, "Введите имя нового оператора:")
        bot.register_next_step_handler(message, update_operator_custom)
    else:
        user_data[message.chat.id]['operator'] = message.text
        show_summary(message.chat.id)

def update_operator_custom(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isalpha():
        bot.send_message(message.chat.id, "Пожалуйста, введите корректное имя оператора: ")
        bot.register_next_step_handler(message, update_operator_custom)
        return
    user_data[message.chat.id]['operator'] = message.text
    show_summary(message.chat.id)

def update_temperature(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    try:
        temperature = float(message.text.replace(",", "."))
    except ValueError:
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение температуры:")
        bot.register_next_step_handler(message, update_temperature)
        return
    user_data[message.chat.id]['temperature'] = message.text
    show_summary(message.chat.id)

def update_comments(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    user_data[message.chat.id]['comments'] = message.text
    show_summary(message.chat.id)

def show_summary(chat_id):
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Всё верно, сохранить данные", "Нужно изменить данные")
    summary = (
        f"Проверьте данные для сохранения в отчет 1/3:\n"
        f"Дата: {user_data[chat_id]['date']}\n"
        f"Оператор: {user_data[chat_id]['operator']}\n"
        f"Температура воздуха: {user_data[chat_id]['temperature']}\n"
        f"Комментарий: {user_data[chat_id]['comments']}"
    )
    bot.send_message(chat_id, summary, reply_markup=markup)

# Функция для записи данных в Google Sheets
def save_to_google_sheets(user_id):
    """Функция для сохранения данных в Google Sheets"""
    data = user_data[user_id]
    
    # Prepare debtor lists with up to 5 entries each, fill with empty strings if less
    ai92_debtors = [f"{debtor['contractor']} - {debtor['volume']} л." for debtor in data['fuel_ai92']['debtors']]
    ai92_debtors += [''] * (5 - len(ai92_debtors))
    
    dt_debtors = [f"{debtor['contractor']} - {debtor['volume']} л." for debtor in data['fuel_dt']['debtors']]
    dt_debtors += [''] * (5 - len(dt_debtors))
    
    # Construct the row data
    row = [
        data['date'],
        data['operator'],
        data['temperature'],
        data['comments'],
        data['fuel_ai92']['sold_cash'],
        data['fuel_ai92']['sold_card'],
        data['fuel_ai92']['total_sold'],
        *ai92_debtors,  # Unpack AI-92 debtors into the row
        data['fuel_dt']['sold_cash'],
        data['fuel_dt']['sold_card'],
        data['fuel_dt']['total_sold'],
        *dt_debtors   # Unpack DT debtors into the row
    ]
    
    # Determine the next available row
    next_row = len(sheet.col_values(1)) + 1  # Find the first empty row in column 1
    
    # Create a list of Cell objects to update
    cells = [gspread.cell.Cell(row=next_row, col=i+1, value=value) for i, value in enumerate(row)]
    
    try:
        # Update the cells in the worksheet
        sheet.update_cells(cells)
    except gspread.exceptions.APIError as e:
        # Handle the API error, e.g., by logging or attempting to add a new row
        print(f"APIError: {e}")
        # Optionally, add a new row and try again
        sheet.add_rows(1)
        sheet.update_cells(cells)

# === Блок 2: Работа с АИ-92-К5 ===

def next_block2(message):
    """Переход к работе с топливом АИ-92-К5"""
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Заполнить данные", callback_data="next"))
    bot.send_message(message.chat.id, "Данные сохранены!\n\nПереходим к следующему разделу отчёта.\nДанные по топливу АИ-92-К5.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "next")
def handle_next_button(call):
    delete_markup = telebot.types.ReplyKeyboardRemove()
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "Показания счетчика АИ-92-К5 (в литрах):", reply_markup=delete_markup)
    bot.register_next_step_handler(call.message, get_ai92_counter)

def get_ai92_counter(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение показаний счетчика: ")
        bot.register_next_step_handler(message, get_ai92_counter)
        return
    user_data[message.chat.id]['fuel_ai92'] = {
    'counter': '',
    'sold_cash': '',
    'sold_card': '',
    'total_sold': '',
    'debtors': []   
    }
    user_data[message.chat.id]['fuel_ai92']['counter'] = message.text
    bot.send_message(message.chat.id, "Продано АИ-92-К5 (в литрах) за наличные:")
    bot.register_next_step_handler(message, get_ai92_sold_cash)

def get_ai92_sold_cash(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение продажи за наличные: ")
        bot.register_next_step_handler(message, get_ai92_sold_cash)
        return
    user_data[message.chat.id]['fuel_ai92']['sold_cash'] = message.text
    bot.send_message(message.chat.id, "Продано АИ-92-К5 (в литрах) по терминалу:")
    bot.register_next_step_handler(message, get_ai92_sold_card)

def get_summary_block2(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    summary = "Проверьте данные для сохранения в отчет 2/3:\n"
    summary += f"Наличные: {user_data[message.chat.id]['fuel_ai92']['sold_cash']} л.\n"
    summary += f"Терминал: {user_data[message.chat.id]['fuel_ai92']['sold_card']} л.\n"
    summary += f"Всего: {user_data[message.chat.id]['fuel_ai92']['total_sold']} л.\n"
    if user_data[message.chat.id]['fuel_ai92']['debtors']:
        summary += "В долг:\n"
        for debtor in user_data[message.chat.id]['fuel_ai92']['debtors']:
            summary += f"Контрагент: {debtor['contractor']}, Сумма: {debtor['volume']} л.\n"
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Всё верно, сохранить данные", "Нужно изменить данные")
    bot.send_message(message.chat.id, summary, reply_markup=markup)
    bot.register_next_step_handler(message, confirm_ai92_data)
        
def get_ai92_sold_card(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение продажи по терминалу: ")
        bot.register_next_step_handler(message, get_ai92_sold_card)
        return
    user_data[message.chat.id]['fuel_ai92']['sold_card'] = message.text
    try:
        sold_cash = int(user_data[message.chat.id]['fuel_ai92']['sold_cash'])
        sold_card = int(user_data[message.chat.id]['fuel_ai92']['sold_card'])
        total_sold = sold_cash + sold_card
        user_data[message.chat.id]['fuel_ai92']['total_sold'] = total_sold
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Сумма АИ-92-К5 за день верна", "Нужно ввести другую сумму АИ-92-К5")
        bot.send_message(message.chat.id, f"Общее количество проданного АИ-92-К5 (в литрах): {total_sold}", reply_markup=markup)
    except (KeyError, ValueError) as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}. Пожалуйста, проверьте введенные данные.")

def get_debt_amount(message):
    if message.text.lower() == "да, отпускали в долг":
        # Prompt to enter multiple debtors
        select_contractor(message)
    else:
        # If no more debtors, move to summary
        if not user_data[message.chat.id]['fuel_ai92']['debtors']:
            user_data[message.chat.id]['fuel_ai92']['debtors'].append({"contractor": "Нет", "volume": 0})
        get_summary_block2(message)

def select_contractor(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    global contractor1, contractor2, contractor3
    contractor1 = "Контрагент 1"
    contractor2 = "Контрагент 2"
    contractor3 = "Контрагент 3"
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(contractor1, contractor2, contractor3, "Другой Контрагент")
    bot.send_message(message.chat.id, "Выберите Контрагента, получившего топливо в долг", reply_markup=markup)
    bot.register_next_step_handler(message, debt_contractor)

def debt_contractor(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if message.text == "Другой Контрагент":
        bot.send_message(message.chat.id, "Введите название контрагента: ")
        bot.register_next_step_handler(message, get_debt_contractor)
    else:
        add_debtor(message, message.text)

def get_debt_contractor(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isalpha():
        bot.send_message(message.chat.id, "Пожалуйста, введите корректное название контрагента: ")
        bot.register_next_step_handler(message, get_debt_contractor)
    else:
        add_debtor(message, message.text)

def add_debtor(message, contractor):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    bot.send_message(message.chat.id, f"Сколько отпущено {contractor} (в литрах): ")
    bot.register_next_step_handler(message, lambda msg: debt_volume(msg, contractor))

def still_debt(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if message.text.lower() == "да, еще отпускали в долг":
        select_contractor(message)
    else:
        get_summary_block2(message)

def debt_volume(message, contractor):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, lambda msg: debt_volume(msg, contractor))
        return
    volume = message.text
    user_data[message.chat.id]['fuel_ai92']['debtors'].append({"contractor": contractor, "volume": volume})
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Да, еще отпускали в долг", "Нет, больше не отпускали")
    bot.send_message(message.chat.id, "Отпускали еще АИ-92-К5 в долг?", reply_markup=markup)
    bot.register_next_step_handler(message, still_debt)

@bot.message_handler(func=lambda message: message.text in ["Сумма АИ-92-К5 за день верна", "Нужно ввести другую сумму АИ-92-К5"])
def handle_total_sold_confirmation(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if message.text == "Сумма АИ-92-К5 за день верна":
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Да, отпускали в долг", "Нет, в долг не отпускали")
        bot.send_message(message.chat.id, "Отпускали АИ-92-К5 в долг?", reply_markup=markup)
        bot.register_next_step_handler(message, get_debt_amount)
    elif message.text == "Нужно ввести другую сумму АИ-92_К5":
        bot.send_message(message.chat.id, "Введите корректную сумму проданного АИ-92-К5 (в литрах): ")
        bot.register_next_step_handler(message, correct_total_sold)

def correct_total_sold(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, correct_total_sold)
        return
    user_data[message.chat.id]['fuel_ai92']['total_sold'] = message.text
    bot.send_message(message.chat.id, "Отпускали АИ-92-К5 в долг?")
    bot.register_next_step_handler(message, get_debt_amount)

@bot.message_handler(func=lambda message: message.text in ["Продажи за наличные", "Продажи по терминалу", "Всего продано", "Отдали в долг", "Нет, всё верно"])
def handle_data_correction_block2(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if message.text == "Нет, всё верно":
        next_block3(message)

    if message.text == "Продажи за наличные":
        bot.send_message(message.chat.id, "Введите новое значение продажи за наличные (в литрах):")
        bot.register_next_step_handler(message, update_ai92_sold_cash)
    
    elif message.text == "Продажи по терминалу":
        bot.send_message(message.chat.id, "Введите новое значение продажи по терминалу (в литрах):")
        bot.register_next_step_handler(message, update_ai92_sold_card)
    
    elif message.text == "Всего продано":
        bot.send_message(message.chat.id, "Введите новое общее количество проданного (в литрах):")
        bot.register_next_step_handler(message, update_ai92_total_sold)
    
    elif message.text == "Отдали в долг":
        # Handle debtors correction
        # For simplicity, assume re-entering debtors
        user_data[message.chat.id]['fuel_ai92']['debtors'] = []
        select_contractor(message)

def update_ai92_sold_cash(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, update_ai92_sold_cash)
        return
    user_data[message.chat.id]['fuel_ai92']['sold_cash'] = message.text
    # Recalculate total_sold if necessary
    try:
        sold_cash = int(user_data[message.chat.id]['fuel_ai92']['sold_cash'])
        sold_card = int(user_data[message.chat.id]['fuel_ai92']['sold_card'])
        total_sold = sold_cash + sold_card
        user_data[message.chat.id]['fuel_ai92']['total_sold'] = total_sold
    except (KeyError, ValueError):
        pass
    get_summary_block2(message)

def update_ai92_sold_card(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, update_ai92_sold_card)
        return
    user_data[message.chat.id]['fuel_ai92']['sold_card'] = message.text
    # Recalculate total_sold if necessary
    try:
        sold_cash = int(user_data[message.chat.id]['fuel_ai92']['sold_cash'])
        sold_card = int(user_data[message.chat.id]['fuel_ai92']['sold_card'])
        total_sold = sold_cash + sold_card
        user_data[message.chat.id]['fuel_ai92']['total_sold'] = total_sold
    except (KeyError, ValueError):
        pass
    get_summary_block2(message)

def update_ai92_total_sold(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, update_ai92_total_sold)
        return
    user_data[message.chat.id]['fuel_ai92']['total_sold'] = message.text
    get_summary_block2(message)

# Handle debtors correction
def select_contractor(message):
    global contractor1, contractor2, contractor3
    contractor1 = "Контрагент 1"
    contractor2 = "Контрагент 2"
    contractor3 = "Контрагент 3"
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(contractor1, contractor2, contractor3, "Другой Контрагент")
    bot.send_message(message.chat.id, "Выберите Контрагента, получившего топливо в долг или нажмите 'Нет, больше не отпускали':", reply_markup=markup)
    bot.register_next_step_handler(message, update_debtors)

def update_debtors(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if message.text.lower() == "нет, больше не отпускали":
        user_data[message.chat.id]['fuel_ai92']['debtors'].append({"contractor": "Нет", "volume": 0})
        get_summary_block2(message)
        return
    if message.text == "Другой Контрагент":
        bot.send_message(message.chat.id, "Введите название контрагента: ")
        bot.register_next_step_handler(message, get_debt_contractor_update)
    else:
        add_debtor_update(message, message.text)

def get_debt_contractor_update(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isalpha():
        bot.send_message(message.chat.id, "Пожалуйста, введите корректное название контрагента: ")
        bot.register_next_step_handler(message, get_debt_contractor_update)
    else:
        add_debtor_update(message, message.text)

def add_debtor_update(message, contractor):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    bot.send_message(message.chat.id, f"Сколько отпущено {contractor} (в литрах): ")
    bot.register_next_step_handler(message, lambda msg: debt_volume_update(msg, contractor))

def debt_volume_update(message, contractor):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, lambda msg: debt_volume_update(msg, contractor))
        return
    volume = message.text
    user_data[message.chat.id]['fuel_ai92']['debtors'].append({"contractor": contractor, "volume": volume})
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Да, еще отпускали в долг", "Нет, больше не отпускали")
    bot.send_message(message.chat.id, "Отпускали еще АИ-92-К5 в долг?", reply_markup=markup)
    bot.register_next_step_handler(message, still_debt_update)

def still_debt_update(message):
    if message.text.lower() == "да, еще отпускали в долг":
        select_contractor(message)
    else:
        get_summary_block2(message)


# === Блок 3: Работа с ДТ ===

def confirm_ai92_data(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if message.text.lower() == "всё верно, сохранить данные":
        next_block3(message)
    if message.text.lower() == "нужно изменить данные":
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Продажи за наличные", "Продажи по терминалу", "Всего продано", "Отдали в долг", "Нет, всё верно")
        bot.send_message(message.chat.id, "Какие данные необходимо исправить?", reply_markup=markup)

# === Блок 3: Работа с ДТ-К5 ===

def next_block3(message):
    """Переход к работе с топливом ДТ-К5"""
    bot.send_message(message.chat.id, "Показания счетчика ДТ-К5 (в литрах):")
    bot.register_next_step_handler(message, get_dt_counter)

def get_dt_counter(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение показаний счетчика: ")
        bot.register_next_step_handler(message, get_dt_counter)
        return
    user_data[message.chat.id]['fuel_dt'] = {
        'counter': '',
        'sold_cash': '',
        'sold_card': '',
        'total_sold': '',
        'debtors': []
    }
    user_data[message.chat.id]['fuel_dt']['counter'] = message.text
    bot.send_message(message.chat.id, "Продано ДТ-К5 (в литрах) за наличные:")
    bot.register_next_step_handler(message, get_dt_sold_cash)

def get_dt_sold_cash(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение продажи за наличные: ")
        bot.register_next_step_handler(message, get_dt_sold_cash)
        return
    user_data[message.chat.id]['fuel_dt']['sold_cash'] = message.text
    bot.send_message(message.chat.id, "Продано ДТ-К5 (в литрах) по терминалу:")
    bot.register_next_step_handler(message, get_dt_sold_card)

def get_dt_sold_card(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение продажи по терминалу: ")
        bot.register_next_step_handler(message, get_dt_sold_card)
        return
    user_data[message.chat.id]['fuel_dt']['sold_card'] = message.text
    try:
        sold_cash = int(user_data[message.chat.id]['fuel_dt']['sold_cash'])
        sold_card = int(user_data[message.chat.id]['fuel_dt']['sold_card'])
        total_sold = sold_cash + sold_card
        user_data[message.chat.id]['fuel_dt']['total_sold'] = total_sold
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Сумма ДТ-К5 за день верна", "Нужно ввести другую сумму ДТ-К5")
        bot.send_message(message.chat.id, f"Общее количество проданного ДТ-К5 (в литрах): {total_sold}", reply_markup=markup)
        bot.register_next_step_handler(message, handle_total_sold_confirmation_block3)
    except (KeyError, ValueError) as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}. Пожалуйста, проверьте введенные данные.")

@bot.message_handler(func=lambda message: message.text in ["Сумма ДТ-К5 за день верна", "Нужно ввести другую сумму ДТ-К5"])
def handle_total_sold_confirmation_block3(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if message.text == "Сумма ДТ-К5 за день верна":
        # Proceed to ask about debtors
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Да, отпускали в долг", "Нет, в долг не отпускали")
        bot.send_message(message.chat.id, "Отпускали ДТ-К5 в долг?", reply_markup=markup)
        bot.register_next_step_handler(message, get_debt_amount_dt)
    elif message.text == "Нужно ввести другую сумму ДТ-К5":
        bot.send_message(message.chat.id, "Введите корректную сумму проданного ДТ-К5 (в литрах): ")
        bot.register_next_step_handler(message, correct_total_sold_dt)

def correct_total_sold_dt(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, correct_total_sold_dt)
        return
    user_data[message.chat.id]['fuel_dt']['total_sold'] = message.text
    # After correcting total sold, ask about debts
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Да, отпускали в долг", "Нет, в долг не отпускали")
    bot.send_message(message.chat.id, "Отпускали ДТ-К5 в долг?", reply_markup=markup)
    bot.register_next_step_handler(message, get_debt_amount_dt)

def get_summary_block3(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    summary = "Проверьте данные для сохранения в отчет 2/3:\n"
    summary += f"Наличные: {user_data[message.chat.id]['fuel_dt']['sold_cash']} л.\n"
    summary += f"Терминал: {user_data[message.chat.id]['fuel_dt']['sold_card']} л.\n"
    summary += f"Всего: {user_data[message.chat.id]['fuel_dt']['total_sold']} л.\n"
    if user_data[message.chat.id]['fuel_dt']['debtors']:
        summary += "В долг:\n"
        for debtor in user_data[message.chat.id]['fuel_dt']['debtors']:
            summary += f"Контрагент: {debtor['contractor']}, Сумма: {debtor['volume']} л.\n"
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Всё верно, сохранить данные", "Нужно изменить данные")
    bot.send_message(message.chat.id, summary, reply_markup=markup)
    bot.register_next_step_handler(message, confirm_dt_data)

@bot.message_handler(func=lambda message: message.text in ["Всё верно, сохранить данные", "Нужно изменить данные"])
def confirm_dt_data(message):
    if message.text == "Всё верно, сохранить данные":
        bot.send_message(message.chat.id, "Данные ДТ-К5 сохранены.")
        save_to_google_sheets(message.chat.id)
    else:
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add("Продажи за наличные", "Продажи по терминалу", "Всего продано", "Отдали в долг", "Нет, всё верно")
        bot.send_message(message.chat.id, "Какие данные необходимо исправить?", reply_markup=markup)
        bot.register_next_step_handler(message, handle_data_correction_block3)

def get_debt_amount_dt(message):
    if message.text == "Да, отпускали в долг":
        select_contractor_dt(message)
    else:
        if not user_data[message.chat.id]['fuel_dt']['debtors']:
            user_data[message.chat.id]['fuel_dt']['debtors'].append({"contractor": "Нет", "volume": 0})
        get_summary_block3(message)

@bot.message_handler(func=lambda message: message.text in ["Продажи за наличные", "Продажи по терминалу", "Всего продано", "Отдали в долг", "Нет, всё верно"])
def handle_data_correction_block3(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if message.text == "Нет, всё верно":
        get_summary_block3(message)
    elif message.text == "Продажи за наличные":
        bot.send_message(message.chat.id, "Введите новое значение продажи за наличные (в литрах):")
        bot.register_next_step_handler(message, update_dt_sold_cash)
    elif message.text == "Продажи по терминалу":
        bot.send_message(message.chat.id, "Введите новое значение продажи по терминалу (в литрах):")
        bot.register_next_step_handler(message, update_dt_sold_card)
    elif message.text == "Всего продано":
        bot.send_message(message.chat.id, "Введите новое общее количество проданного (в литрах):")
        bot.register_next_step_handler(message, update_dt_total_sold)
    elif message.text == "Отдали в долг":
        user_data[message.chat.id]['fuel_dt']['debtors'] = []
        select_contractor_dt(message)

def update_dt_sold_cash(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, update_dt_sold_cash)
        return
    user_data[message.chat.id]['fuel_dt']['sold_cash'] = message.text
    # Recalculate total_sold if necessary
    try:
        sold_cash = int(user_data[message.chat.id]['fuel_dt']['sold_cash'])
        sold_card = int(user_data[message.chat.id]['fuel_dt']['sold_card'])
        total_sold = sold_cash + sold_card
        user_data[message.chat.id]['fuel_dt']['total_sold'] = total_sold
    except (KeyError, ValueError):
        pass
    get_summary_block3(message)

def update_dt_sold_card(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, update_dt_sold_card)
        return
    user_data[message.chat.id]['fuel_dt']['sold_card'] = message.text
    # Recalculate total_sold if necessary
    try:
        sold_cash = int(user_data[message.chat.id]['fuel_dt']['sold_cash'])
        sold_card = int(user_data[message.chat.id]['fuel_dt']['sold_card'])
        total_sold = sold_cash + sold_card
        user_data[message.chat.id]['fuel_dt']['total_sold'] = total_sold
    except (KeyError, ValueError):
        pass
    get_summary_block3(message)

def update_dt_total_sold(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, update_dt_total_sold)
        return
    user_data[message.chat.id]['fuel_dt']['total_sold'] = message.text
    get_summary_block3(message)

def select_contractor_dt(message):
    global contractor1, contractor2, contractor3
    contractor1 = "Контрагент 1"
    contractor2 = "Контрагент 2"
    contractor3 = "Контрагент 3"
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(contractor1, contractor2, contractor3, "Другой Контрагент", "Нет, больше не отпускали")
    bot.send_message(message.chat.id, "Выберите Контрагента, получившего топливо в долг или нажмите 'Нет, больше не отпускали':", reply_markup=markup)
    bot.register_next_step_handler(message, debt_contractor_dt)

def debt_contractor_dt(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if message.text == "Другой Контрагент":
        bot.send_message(message.chat.id, "Введите название контрагента: ")
        bot.register_next_step_handler(message, get_debt_contractor_dt)
    elif message.text == "Нет, больше не отпускали":
        if not user_data[message.chat.id]['fuel_dt']['debtors']:
            user_data[message.chat.id]['fuel_dt']['debtors'].append({"contractor": "Нет", "volume": 0})
        get_summary_block3(message)
    else:
        add_debtor_dt(message, message.text)

def get_debt_contractor_dt(message):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isalpha():
        bot.send_message(message.chat.id, "Пожалуйста, введите корректное название контрагента: ")
        bot.register_next_step_handler(message, get_debt_contractor_dt)
    else:
        add_debtor_dt(message, message.text)

def add_debtor_dt(message, contractor):
    bot.send_message(message.chat.id, f"Сколько отпущено {contractor} (в литрах): ")
    bot.register_next_step_handler(message, lambda msg: debt_volume_dt(msg, contractor))

def debt_volume_dt(message, contractor):
    if message.text.startswith('/'):
            handle_commands(message)  # Перенаправляем команды
            return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Пожалуйста, введите числовое значение: ")
        bot.register_next_step_handler(message, lambda msg: debt_volume_dt(msg, contractor))
        return
    volume = message.text
    user_data[message.chat.id]['fuel_dt']['debtors'].append({"contractor": contractor, "volume": volume})
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Да, еще отпускали в долг", "Нет, больше не отпускали")
    bot.send_message(message.chat.id, "Отпускали еще ДТ-К5 в долг?", reply_markup=markup)
    bot.register_next_step_handler(message, still_debt_dt)

def still_debt_dt(message):
    if message.text.lower() == "да, еще отпускали в долг":
        select_contractor_dt(message)
    else:
        get_summary_block3(message)

# Запуск бота
bot.polling()