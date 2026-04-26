import sqlite3
import os
import random
import asyncio
import zipfile
import requests
import io
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import ReportSpamRequest
from telethon.tl.types import InputReportReasonSpam, InputReportReasonFake, InputReportReasonViolence, InputReportReasonChildAbuse, InputReportReasonOther
import telebot
from telebot import types
from pyCryptoPayAPI import pyCryptoPayAPI
import config

# ========== АВТОЗАГРУЗКА СЕССИЙ ==========
SESSIONS_URL = os.getenv('SESSIONS_URL')
if SESSIONS_URL and not os.path.exists(config.SESSION_FOLDER):
    print("🔄 Загружаю сессии...")
    try:
        os.makedirs(config.SESSION_FOLDER, exist_ok=True)
        r = requests.get(SESSIONS_URL, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            zf.extractall(config.SESSION_FOLDER)
        count = len([f for f in os.listdir(config.SESSION_FOLDER) if f.endswith('.session')])
        print(f"✅ Загружено {count} сессий")
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
# ========================================

reasons = [
    InputReportReasonSpam(),
    InputReportReasonFake(),
    InputReportReasonViolence(),
    InputReportReasonChildAbuse(),
    InputReportReasonOther()
]

bot = telebot.TeleBot(config.TOKEN)
crypto = pyCryptoPayAPI(api_token=config.CRYPTO)

session_folder = config.SESSION_FOLDER
os.makedirs(session_folder, exist_ok=True)

sessions = [f.replace('.session', '') for f in os.listdir(session_folder) if f.endswith('.session')]
last_used = {}

# ========== КЛАВИАТУРЫ ==========
menu = types.InlineKeyboardMarkup(row_width=2)
profile = types.InlineKeyboardButton("👤 Профиль", callback_data='profile')
shop = types.InlineKeyboardButton("🛒 Подписка", callback_data='shop')
snoser = types.InlineKeyboardButton("🚀 Запуск", callback_data='snoser')
menu.add(profile, shop, snoser)

back_markup = types.InlineKeyboardMarkup(row_width=1)
back = types.InlineKeyboardButton("🔙 Назад", callback_data='back')
back_markup.add(back)

admin_markup = types.InlineKeyboardMarkup(row_width=2)
add_subsribe = types.InlineKeyboardButton("Выдать подписку", callback_data='add_subsribe')
clear_subscribe = types.InlineKeyboardButton("Забрать подписку", callback_data='clear_subscribe')
send_all = types.InlineKeyboardButton("Рассылка", callback_data='send_all')
admin_markup.add(add_subsribe, clear_subscribe, send_all)

shop_markup = types.InlineKeyboardMarkup(row_width=2)
sub_1 = types.InlineKeyboardButton("1 день", callback_data='sub_1')
sub_2 = types.InlineKeyboardButton("7 дней", callback_data='sub_2')
sub_4 = types.InlineKeyboardButton("30 дней", callback_data='sub_4')
sub_6 = types.InlineKeyboardButton("Навсегда", callback_data='sub_6')
shop_markup.add(sub_1, sub_2, sub_4, sub_6, back)

# ========== БАЗА ДАННЫХ ==========
def check_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    res = c.fetchone()
    conn.close()
    return res is not None

def extract_channel_and_id(url):
    try:
        if 't.me/c/' in url:
            parts = url.split('/')
            chat_id = int('-100' + parts[4])
            msg_id = int(parts[5])
            return str(chat_id), msg_id
        else:
            path = url[len('https://t.me/'):].split('/')
            if len(path) == 2:
                return path[0], int(path[1])
        raise ValueError("Неверный формат")
    except:
        raise ValueError("Неверный формат")

# ========== ОТПРАВКА ЖАЛОБ ==========
async def send_reports(chat_username, msg_id, user_id):
    ok = 0
    fail = 0
    flood = 0

    for ses in sessions:
        api_id = config.API_ID
        api_hash = config.API_HASH
        session_file = os.path.join(session_folder, ses + ".session")
        session_path = os.path.join(session_folder, ses)

        if not os.path.exists(session_file):
            fail += 1
            continue

        client = TelegramClient(session_path, api_id, api_hash, system_version='4.16.30-vxCUSTOM', sequential_updates=True)

        try:
            await client.connect()
            if not await client.is_user_authorized():
                fail += 1
                await client.disconnect()
                continue

            chat = await client.get_entity(chat_username)
            await client(ReportSpamRequest(peer=chat))
            ok += 1
            await client.disconnect()
        except FloodWaitError as e:
            flood += 1
            await client.disconnect()
        except Exception:
            fail += 1
            await client.disconnect()
            continue

    bot.send_message(user_id, f"🚀 Готово!\n✅ Удачно: {ok}\n❌ Ошибок: {fail}\n🌊 Flood: {flood}", reply_markup=back_markup)

# ========== КОМАНДЫ БОТА ==========
@bot.message_handler(commands=['start'])
def start(msg):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users(user_id BIGINT, subscribe DATETIME)''')
    uid = msg.chat.id
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,))
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES(?, ?)", (uid, "1999-01-01 20:00:00"))
        conn.commit()
    bot.send_message(uid, "⚡️ Бот запущен", reply_markup=menu, parse_mode="Markdown")
    conn.close()

@bot.callback_query_handler(lambda c: c.data and c.data.startswith('sub_'))
def handle_sub(call):
    uid = call.from_user.id
    if not check_user(uid):
        bot.send_message(uid, "❌ Ошибка")
        return
    typ = call.data.split('_')[1]
    if typ == "1":
        inv = crypto.create_invoice('USDT', 2)
        days = "1"
        amount = 2
    elif typ == "2":
        inv = crypto.create_invoice('USDT', 7)
        days = "7"
        amount = 7
    elif typ == "4":
        inv = crypto.create_invoice('USDT', 15)
        days = "30"
        amount = 15
    else:
        inv = crypto.create_invoice('USDT', 30)
        days = "9999"
        amount = 30

    payurl = inv['pay_url']
    inv_id = inv['invoice_id']
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💸 Оплатить", url=payurl),
               types.InlineKeyboardButton("✅ Проверить", callback_data=f"check_{inv_id}_{days}"),
               back)
    bot.edit_message_text(f"Оплата {days} дней, {amount}$", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(lambda c: c.data and c.data.startswith('check_'))
def check_pay(call):
    uid = call.from_user.id
    if not check_user(uid):
        return
    _, inv_id, days = call.data.split('_')
    try:
        inv = crypto.get_invoices(invoice_ids=inv_id)
        if inv['items'][0]['status'] == 'paid':
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            new_date = (datetime.now() + timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
            c.execute("UPDATE users SET subscribe = ? WHERE user_id = ?", (new_date, uid))
            conn.commit()
            conn.close()
            bot.edit_message_text("✅ Оплачено!", call.message.chat.id, call.message.message_id, reply_markup=back_markup)
        else:
            bot.answer_callback_query(call.id, "⏳ Не оплачено", show_alert=True)
    except:
        bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=True)

@bot.callback_query_handler(func=lambda call: True)
def main_callback(call):
    uid = call.from_user.id
    if not check_user(uid):
        bot.send_message(uid, "❌ Ошибка")
        return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    sub_str = c.execute("SELECT subscribe FROM users WHERE user_id = ?", (uid,)).fetchone()[0]
    sub_date = datetime.strptime(sub_str, "%Y-%m-%d %H:%M:%S")

    if call.data == 'snoser':
        if sub_date < datetime.now():
            bot.send_message(uid, "⏳ Подписка истекла")
            conn.close()
            return
        if uid in last_used and (datetime.now() - last_used[uid]) < timedelta(minutes=5):
            sec = int((timedelta(minutes=5) - (datetime.now() - last_used[uid])).total_seconds())
            bot.send_message(uid, f"⏳ Ждите {sec} секунд")
            conn.close()
            return
        last_used[uid] = datetime.now()
        m = bot.send_message(uid, "🔗 Введите ссылку на сообщение:")
        bot.register_next_step_handler(m, process_link)
    elif call.data == 'back':
        bot.edit_message_text("⚡️ Меню", call.message.chat.id, call.message.message_id, reply_markup=menu)
    elif call.data == 'profile':
        bot.edit_message_text(f"👤 ID: {uid}\n📅 Подписка до: {sub_date}", call.message.chat.id, call.message.message_id, reply_markup=back_markup)
    elif call.data == 'shop':
        bot.edit_message_text("💸 Цены:\n1 день — 2$\n7 дней — 7$\n30 дней — 15$\nНавсегда — 30$", call.message.chat.id, call.message.message_id, reply_markup=shop_markup)
    elif call.data == 'add_subsribe' and call.from_user.id in config.ADMINS:
        m = bot.send_message(uid, "Введите ID пользователя:")
        bot.register_next_step_handler(m, add_sub2)
    elif call.data == 'clear_subscribe' and call.from_user.id in config.ADMINS:
        m = bot.send_message(uid, "Введите ID пользователя:")
        bot.register_next_step_handler(m, clear_sub2)
    elif call.data == 'send_all' and call.from_user.id in config.ADMINS:
        m = bot.send_message(uid, "Введите текст рассылки:")
        bot.register_next_step_handler(m, send_all_text)
    conn.close()

def process_link(msg):
    url = msg.text
    uid = msg.from_user.id
    try:
        ch, mid = extract_channel_and_id(url)
        bot.send_message(uid, "🚀 Запускаю...")
        asyncio.run(send_reports(ch, mid, uid))
    except ValueError:
        bot.send_message(uid, "❌ Неверная ссылка")

def add_sub2(msg):
    if msg.from_user.id not in config.ADMINS:
        return
    uid = int(msg.text)
    m2 = bot.send_message(msg.chat.id, "Введите количество дней:")
    bot.register_next_step_handler(m2, add_sub3, uid)

def add_sub3(msg, uid):
    if msg.from_user.id not in config.ADMINS:
        return
    days = int(msg.text)
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    new_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE users SET subscribe = ? WHERE user_id = ?", (new_date, uid))
    conn.commit()
    conn.close()
    bot.send_message(msg.chat.id, "✅ Готово")

def clear_sub2(msg):
    if msg.from_user.id not in config.ADMINS:
        return
    uid = int(msg.text)
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET subscribe = ? WHERE user_id = ?", ("1999-01-01 20:00:00", uid))
    conn.commit()
    conn.close()
    bot.send_message(msg.chat.id, "✅ Сброшено")

def send_all_text(msg):
    if msg.from_user.id not in config.ADMINS:
        return
    txt = msg.text
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    users = c.execute("SELECT user_id FROM users").fetchall()
    ok = 0
    for u in users:
        try:
            bot.send_message(u[0], txt)
            ok += 1
        except:
            pass
    bot.send_message(msg.chat.id, f"✅ Отправлено {ok} пользователям")
    conn.close()

@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if msg.from_user.id in config.ADMINS:
        bot.send_message(msg.chat.id, "👑 Админ панель", reply_markup=admin_markup)

if __name__ == '__main__':
    print("🚀 Бот запущен")
    bot.polling(none_stop=True)
