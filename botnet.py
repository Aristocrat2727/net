import sqlite3
import os
import random
import asyncio
import zipfile
import requests
import io
import secrets
import shutil
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import InputReportReasonSpam, InputReportReasonFake, InputReportReasonViolence, InputReportReasonChildAbuse, InputReportReasonOther
import telebot
from telebot import types
from pyCryptoPayAPI import pyCryptoPayAPI
import config

# ========== АВТОЗАГРУЗКА СЕССИЙ ==========
SESSIONS_URL = os.getenv('SESSIONS_URL')
SESSION_FOLDER = config.SESSION_FOLDER

if SESSIONS_URL and not os.path.exists(SESSION_FOLDER):
    print("🔄 Загружаю сессии...")
    try:
        os.makedirs(SESSION_FOLDER, exist_ok=True)
        print(f"📥 Скачиваю архив с {SESSIONS_URL}")
        r = requests.get(SESSIONS_URL, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            zf.extractall(SESSION_FOLDER)
        
        # Если внутри архива оказалась папка, перемещаем содержимое
        for item in os.listdir(SESSION_FOLDER):
            item_path = os.path.join(SESSION_FOLDER, item)
            if os.path.isdir(item_path):
                for subitem in os.listdir(item_path):
                    shutil.move(os.path.join(item_path, subitem), SESSION_FOLDER)
                os.rmdir(item_path)
        
        count = len([f for f in os.listdir(SESSION_FOLDER) if f.endswith('.session')])
        print(f"✅ Загружено {count} сессий")
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
# ========================================

reasons_map = {
    "spam": InputReportReasonSpam(),
    "fake": InputReportReasonFake(),
    "violence": InputReportReasonViolence(),
    "child": InputReportReasonChildAbuse(),
    "other": InputReportReasonOther()
}

bot = telebot.TeleBot(config.TOKEN)
crypto = pyCryptoPayAPI(api_token=config.CRYPTO)

session_folder = config.SESSION_FOLDER
os.makedirs(session_folder, exist_ok=True)

sessions = [f.replace('.session', '') for f in os.listdir(session_folder) if f.endswith('.session')]
last_used = {}
user_data = {}

# ========== КЛАВИАТУРЫ ==========
menu = types.InlineKeyboardMarkup(row_width=2)
profile = types.InlineKeyboardButton("👤 Профиль", callback_data='profile')
shop = types.InlineKeyboardButton("🛒 Подписка", callback_data='shop')
snoser = types.InlineKeyboardButton("🚀 Жалоба на сообщение", callback_data='snoser')
scam_btn = types.InlineKeyboardButton("🎭 Scam репорт (канал)", callback_data='scam_report')
menu.add(profile, shop, snoser, scam_btn)

back_markup = types.InlineKeyboardMarkup(row_width=1)
back = types.InlineKeyboardButton("🔙 Назад", callback_data='back')
back_markup.add(back)

admin_markup = types.InlineKeyboardMarkup(row_width=2)
add_subsribe = types.InlineKeyboardButton("➕ Выдать подписку", callback_data='add_subsribe')
clear_subscribe = types.InlineKeyboardButton("❌ Забрать подписку", callback_data='clear_subscribe')
send_all = types.InlineKeyboardButton("📢 Рассылка", callback_data='send_all')
add_promo = types.InlineKeyboardButton("🎫 Создать промокод", callback_data='add_promo')
view_promos = types.InlineKeyboardButton("📋 Список промокодов", callback_data='view_promos')
admin_markup.add(add_subsribe, clear_subscribe, send_all)
admin_markup.add(add_promo, view_promos)

shop_markup = types.InlineKeyboardMarkup(row_width=2)
sub_1 = types.InlineKeyboardButton("1 день - 2$", callback_data='sub_1')
sub_2 = types.InlineKeyboardButton("7 дней - 7$", callback_data='sub_2')
sub_4 = types.InlineKeyboardButton("30 дней - 15$", callback_data='sub_4')
sub_6 = types.InlineKeyboardButton("Навсегда - 30$", callback_data='sub_6')
promo_btn = types.InlineKeyboardButton("🎫 Ввести промокод", callback_data='enter_promo')
shop_markup.add(sub_1, sub_2, sub_4, sub_6)
shop_markup.add(promo_btn, back)

scam_markup = types.InlineKeyboardMarkup(row_width=2)
scam_markup.add(
    types.InlineKeyboardButton("💸 Ложные финансовые обещания", callback_data="scam_reason_finance"),
    types.InlineKeyboardButton("🎭 Выдача себя за другое лицо", callback_data="scam_reason_fake"),
    types.InlineKeyboardButton("💀 Вредоносное ПО/фишинг", callback_data="scam_reason_malware"),
    types.InlineKeyboardButton("📦 Сомнительный продавец", callback_data="scam_reason_seller"),
    types.InlineKeyboardButton("🔄 Другое", callback_data="scam_reason_other")
)
scam_markup.add(back)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        subscribe TEXT,
        username TEXT,
        first_name TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS promocodes(
        code TEXT PRIMARY KEY,
        days INTEGER,
        used_by INTEGER,
        created_by INTEGER,
        created_at TEXT,
        used_at TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def get_sub_status(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT subscribe FROM users WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def has_sub(user_id):
    sub = get_sub_status(user_id)
    if not sub or sub == "None" or sub == "0":
        return False
    try:
        sub_date = datetime.strptime(sub, "%Y-%m-%d %H:%M:%S")
        return sub_date > datetime.now()
    except:
        return False

def set_sub(user_id, days):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    current = get_sub_status(user_id)
    if current and current != "None" and current != "0":
        try:
            old_date = datetime.strptime(current, "%Y-%m-%d %H:%M:%S")
            if old_date > datetime.now():
                new_date = old_date + timedelta(days=days)
            else:
                new_date = datetime.now() + timedelta(days=days)
        except:
            new_date = datetime.now() + timedelta(days=days)
    else:
        new_date = datetime.now() + timedelta(days=days)
    
    new_date_str = new_date.strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR REPLACE INTO users (user_id, subscribe) VALUES (?, ?)", (user_id, new_date_str))
    conn.commit()
    conn.close()
    return new_date_str

def remove_sub(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET subscribe = 'None' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def create_promo_code(days, admin_id):
    code = secrets.token_hex(8).upper()
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT INTO promocodes (code, days, created_by, created_at) VALUES (?, ?, ?, ?)",
              (code, days, admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return code

def use_promo_code(user_id, code):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT days, used_by FROM promocodes WHERE code = ?", (code,))
    res = c.fetchone()
    if not res:
        conn.close()
        return False, "Промокод не найден"
    days, used_by = res
    if used_by:
        conn.close()
        return False, "Промокод уже использован"
    c.execute("UPDATE promocodes SET used_by = ?, used_at = ? WHERE code = ?", (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), code))
    conn.commit()
    conn.close()
    set_sub(user_id, days)
    return True, f"Подписка активирована на {days} дней"

def get_promocodes():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT code, days, used_by, created_at FROM promocodes ORDER BY created_at DESC")
    res = c.fetchall()
    conn.close()
    return res

def check_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, subscribe) VALUES (?, 'None')", (user_id,))
    conn.commit()
    conn.close()
    return True

def extract_channel_and_id(url):
    try:
        if 't.me/c/' in url:
            parts = url.split('/')
            chat_id = int('-100' + parts[4])
            msg_id = int(parts[5])
            return str(chat_id), msg_id
        else:
            path = url[len('https://t.me/'):].split('/')
            if len(path) >= 2:
                return path[0], int(path[1])
        raise ValueError("Неверный формат")
    except:
        raise ValueError("Неверный формат")

def extract_channel_only(url):
    try:
        username = url.split('t.me/')[-1].split('/')[0].split('?')[0]
        return username
    except:
        raise ValueError("Неверная ссылка на канал")

# ========== ОТПРАВКА ЖАЛОБ НА СООБЩЕНИЕ ==========
async def send_reports(chat_username, msg_id, user_id):
    ok = 0
    fail = 0
    flood = 0

    print(f"🔍 Отладка: папка сессий = {session_folder}")
    print(f"🔍 Отладка: список сессий = {sessions}")
    if not sessions:
        bot.send_message(user_id, "❌ Нет сессий! Проверь SESSIONS_URL и архив.")
        return

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
            reason = random.choice(list(reasons_map.values()))
            
            await client(ReportRequest(
                peer=chat,
                id=[msg_id],
                reason=reason,
                message=""
            ))
            ok += 1
            await client.disconnect()
        except FloodWaitError as e:
            flood += 1
            await client.disconnect()
        except Exception as e:
            fail += 1
            await client.disconnect()
            continue

    bot.send_message(user_id, f"🚀 Жалоба на сообщение!\n✅ Успешно: {ok}\n❌ Ошибок: {fail}\n🌊 Flood: {flood}", reply_markup=back_markup)

# ========== ОТПРАВКА ЖАЛОБ НА КАНАЛ (SCAM) ==========
async def send_scam_report(channel, reason, comment, user_id):
    ok = 0
    fail = 0
    
    reason_map = {
        'finance': 'Ложные финансовые обещания',
        'fake': 'Выдача себя за другое лицо',
        'malware': 'Вредоносное ПО/фишинг',
        'seller': 'Сомнительный продавец',
        'other': 'Другое'
    }
    reason_text = reason_map.get(reason, 'Мошенничество')
    full_text = f"Reason: {reason_text}\nComment: {comment}" if comment else f"Reason: {reason_text}"
    
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
            
            chat = await client.get_entity(channel)
            
            await client(ReportRequest(
                peer=chat,
                id=[],  # пустой = жалоба на весь канал
                reason=InputReportReasonOther(),
                message=full_text
            ))
            ok += 1
            await client.disconnect()
        except Exception as e:
            fail += 1
            await client.disconnect()
            continue
    
    bot.send_message(user_id, f"🎭 Scam-репорт!\n✅ Успешно: {ok}\n❌ Ошибок: {fail}", reply_markup=back_markup)

# ========== КОМАНДЫ БОТА ==========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    username = msg.from_user.username or ""
    first_name = msg.from_user.first_name or ""
    check_user(uid)
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET username = ?, first_name = ? WHERE user_id = ?", (username, first_name, uid))
    conn.commit()
    conn.close()
    
    bot.send_message(uid, "⚡️ Бот запущен!\nКупи подписку или введи промокод.", reply_markup=menu, parse_mode="Markdown")

@bot.callback_query_handler(lambda c: c.data and c.data.startswith('sub_'))
def handle_sub(call):
    uid = call.from_user.id
    check_user(uid)
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
    elif typ == "6":
        inv = crypto.create_invoice('USDT', 30)
        days = "9999"
        amount = 30
    else:
        inv = crypto.create_invoice('USDT', 2)
        days = "1"
        amount = 2

    payurl = inv['pay_url']
    inv_id = inv['invoice_id']
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💸 Оплатить", url=payurl),
               types.InlineKeyboardButton("✅ Проверить", callback_data=f"check_{inv_id}_{days}"),
               back)
    bot.edit_message_text(f"💸 Оплата {days} дней, {amount}$", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(lambda c: c.data and c.data.startswith('check_'))
def check_pay(call):
    uid = call.from_user.id
    _, inv_id, days = call.data.split('_')
    try:
        inv = crypto.get_invoices(invoice_ids=inv_id)
        if inv['items'][0]['status'] == 'paid':
            days_int = int(days) if days != "9999" else 9999
            set_sub(uid, days_int)
            bot.edit_message_text("✅ Оплачено! Подписка активна.", call.message.chat.id, call.message.message_id, reply_markup=back_markup)
            if config.bot_logs:
                bot.send_message(config.bot_logs, f"💰 Оплата от {uid} на {days} дней")
        else:
            bot.answer_callback_query(call.id, "⏳ Ещё не оплачено", show_alert=True)
    except:
        bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=True)

@bot.callback_query_handler(lambda c: c.data == 'enter_promo')
def enter_promo(call):
    uid = call.from_user.id
    check_user(uid)
    msg = bot.send_message(uid, "🎫 Введите промокод:")
    bot.register_next_step_handler(msg, process_promo)

def process_promo(msg):
    uid = msg.from_user.id
    code = msg.text.strip().upper()
    success, message = use_promo_code(uid, code)
    if success:
        bot.send_message(uid, f"✅ {message}", reply_markup=menu)
    else:
        bot.send_message(uid, f"❌ {message}", reply_markup=shop_markup)

@bot.callback_query_handler(lambda c: c.data == 'add_promo' and c.from_user.id in config.ADMINS)
def add_promo_cmd(call):
    uid = call.from_user.id
    msg = bot.send_message(uid, "🎫 Введите количество дней для промокода:")
    bot.register_next_step_handler(msg, add_promo_days)

def add_promo_days(msg):
    if msg.from_user.id not in config.ADMINS:
        return
    try:
        days = int(msg.text)
        code = create_promo_code(days, msg.from_user.id)
        bot.send_message(msg.chat.id, f"✅ Промокод создан:\n`{code}`\nНа {days} дней", parse_mode="Markdown")
    except:
        bot.send_message(msg.chat.id, "❌ Ошибка. Введите число.")

@bot.callback_query_handler(lambda c: c.data == 'view_promos' and c.from_user.id in config.ADMINS)
def view_promos(call):
    promos = get_promocodes()
    if not promos:
        bot.send_message(call.from_user.id, "📋 Промокодов нет")
        return
    text = "📋 **Список промокодов:**\n\n"
    for code, days, used_by, created_at in promos:
        status = "❌ Использован" if used_by else "✅ Активен"
        text += f"`{code}` - {days} дней - {status}\n"
    bot.send_message(call.from_user.id, text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def main_callback(call):
    uid = call.from_user.id
    check_user(uid)
    has_active = has_sub(uid)

    if call.data == 'snoser':
        if not has_active:
            bot.send_message(uid, "❌ У вас нет активной подписки!", reply_markup=shop_markup)
            return
        if uid in last_used and (datetime.now() - last_used[uid]) < timedelta(minutes=5):
            sec = int((timedelta(minutes=5) - (datetime.now() - last_used[uid])).total_seconds())
            bot.send_message(uid, f"⏳ Ждите {sec} секунд")
            return
        last_used[uid] = datetime.now()
        m = bot.send_message(uid, "🔗 Введите ссылку на сообщение:\nhttps://t.me/username/12345")
        bot.register_next_step_handler(m, process_link)
    
    elif call.data == 'scam_report':
        if not has_active:
            bot.send_message(uid, "❌ У вас нет активной подписки!", reply_markup=shop_markup)
            return
        if uid in last_used and (datetime.now() - last_used[uid]) < timedelta(minutes=5):
            sec = int((timedelta(minutes=5) - (datetime.now() - last_used[uid])).total_seconds())
            bot.send_message(uid, f"⏳ Ждите {sec} секунд")
            return
        last_used[uid] = datetime.now()
        m = bot.send_message(uid, "🔗 Введите ссылку на **канал**:\nhttps://t.me/username")
        bot.register_next_step_handler(m, process_scam_channel)
    
    elif call.data.startswith('scam_reason_'):
        if uid not in user_data:
            bot.send_message(uid, "❌ Ошибка, начните заново /start")
            return
        reason = call.data.split('_')[2]
        user_data[uid]['scam_reason'] = reason
        msg = bot.send_message(uid, "📝 Введите комментарий (или '-' чтобы пропустить):")
        bot.register_next_step_handler(msg, process_scam_comment)
    
    elif call.data == 'back':
        bot.edit_message_text("⚡️ Главное меню", call.message.chat.id, call.message.message_id, reply_markup=menu)
    
    elif call.data == 'profile':
        sub_status = get_sub_status(uid)
        if sub_status and sub_status != "None" and sub_status != "0":
            try:
                sub_date = datetime.strptime(sub_status, "%Y-%m-%d %H:%M:%S")
                if sub_date > datetime.now():
                    remaining = sub_date - datetime.now()
                    days = remaining.days
                    hours = remaining.seconds // 3600
                    text = f"👤 ID: {uid}\n📅 Подписка до: {sub_date}\n⏰ Осталось: {days} дн. {hours} ч."
                else:
                    text = f"👤 ID: {uid}\n❌ Подписка не активна"
            except:
                text = f"👤 ID: {uid}\n❌ Подписка не активна"
        else:
            text = f"👤 ID: {uid}\n❌ Подписка не активна"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_markup)
    
    elif call.data == 'shop':
        bot.edit_message_text("💸 **Магазин подписок:**\n\n1 день — 2$\n7 дней — 7$\n30 дней — 15$\nНавсегда — 30$", 
                              call.message.chat.id, call.message.message_id, reply_markup=shop_markup, parse_mode="Markdown")
    
    elif call.data == 'add_subsribe' and call.from_user.id in config.ADMINS:
        m = bot.send_message(uid, "➕ Введите ID пользователя и количество дней через пробел:\nПример: `123456789 30`", parse_mode="Markdown")
        bot.register_next_step_handler(m, add_sub2)
    
    elif call.data == 'clear_subscribe' and call.from_user.id in config.ADMINS:
        m = bot.send_message(uid, "❌ Введите ID пользователя для удаления подписки:")
        bot.register_next_step_handler(m, clear_sub2)
    
    elif call.data == 'send_all' and call.from_user.id in config.ADMINS:
        m = bot.send_message(uid, "📢 Введите текст рассылки:")
        bot.register_next_step_handler(m, send_all_text)

def process_link(msg):
    url = msg.text
    uid = msg.from_user.id
    try:
        ch, mid = extract_channel_and_id(url)
        bot.send_message(uid, "🚀 Запускаю жалобу на сообщение...")
        asyncio.run(send_reports(ch, mid, uid))
    except ValueError as e:
        bot.send_message(uid, f"❌ {e}")

def process_scam_channel(msg):
    uid = msg.from_user.id
    url = msg.text.strip()
    try:
        channel = extract_channel_only(url)
        user_data[uid] = {'scam_channel': channel}
        bot.send_message(uid, "🎭 Выберите причину:", reply_markup=scam_markup)
    except ValueError as e:
        bot.send_message(uid, f"❌ {e}")

def process_scam_comment(msg):
    uid = msg.from_user.id
    comment = msg.text.strip()
    if comment == '-':
        comment = ''
    
    if uid not in user_data or 'scam_channel' not in user_data or 'scam_reason' not in user_data:
        bot.send_message(uid, "❌ Ошибка, начните заново /start")
        return
    
    channel = user_data[uid]['scam_channel']
    reason = user_data[uid]['scam_reason']
    
    bot.send_message(uid, "🎭 Запускаю Scam-репорт...")
    asyncio.run(send_scam_report(channel, reason, comment, uid))
    
    del user_data[uid]

def add_sub2(msg):
    if msg.from_user.id not in config.ADMINS:
        return
    try:
        parts = msg.text.split()
        uid = int(parts[0])
        days = int(parts[1])
        set_sub(uid, days)
        bot.send_message(msg.chat.id, f"✅ Пользователю {uid} выдана подписка на {days} дней")
        bot.send_message(uid, f"✅ Администратор выдал вам подписку на {days} дней!")
    except:
        bot.send_message(msg.chat.id, "❌ Ошибка. Используй: `123456789 30`", parse_mode="Markdown")

def clear_sub2(msg):
    if msg.from_user.id not in config.ADMINS:
        return
    try:
        uid = int(msg.text)
        remove_sub(uid)
        bot.send_message(msg.chat.id, f"✅ Подписка пользователя {uid} удалена")
        bot.send_message(uid, "❌ Ваша подписка была удалена администратором")
    except:
        bot.send_message(msg.chat.id, "❌ Ошибка. Введите ID пользователя")

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
            bot.send_message(u[0], f"📢 **Рассылка**\n\n{txt}", parse_mode="Markdown")
            ok += 1
        except:
            pass
    bot.send_message(msg.chat.id, f"✅ Отправлено {ok} пользователям")
    conn.close()

@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if msg.from_user.id in config.ADMINS:
        bot.send_message(msg.chat.id, "👑 **Админ панель**", reply_markup=admin_markup, parse_mode="Markdown")

if __name__ == '__main__':
    print("🚀 Бот запущен")
    bot.polling(none_stop=True)
