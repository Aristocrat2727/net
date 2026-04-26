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

if SESSIONS_URL:
    print("🔄 Загружаю сессии...")
    try:
        if os.path.exists(SESSION_FOLDER):
            shutil.rmtree(SESSION_FOLDER)
        os.makedirs(SESSION_FOLDER, exist_ok=True)
        r = requests.get(SESSIONS_URL, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            zf.extractall(SESSION_FOLDER)
        nested = os.path.join(SESSION_FOLDER, "sessions")
        if os.path.isdir(nested):
            for f in os.listdir(nested):
                shutil.move(os.path.join(nested, f), SESSION_FOLDER)
            os.rmdir(nested)
        count = len([f for f in os.listdir(SESSION_FOLDER) if f.endswith('.session')])
        print(f"✅ Загружено {count} сессий")
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
else:
    print("⚠️ SESSIONS_URL не задана")

print(f"🔍 Папка сессий: {SESSION_FOLDER}")
print(f"🔍 Файлы в папке: {os.listdir(SESSION_FOLDER) if os.path.exists(SESSION_FOLDER) else 'папки нет'}")
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

print(f"🔍 Найдено сессий: {len(sessions)}")

# ========== БАЗЫ ДАННЫХ ==========
conn = sqlite3.connect('user_data.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS temp_data(
    user_id INTEGER PRIMARY KEY,
    scam_channel TEXT,
    scam_reason TEXT
)''')
conn.commit()

def save_temp_data(user_id, channel, reason):
    c.execute("INSERT OR REPLACE INTO temp_data (user_id, scam_channel, scam_reason) VALUES (?, ?, ?)", (user_id, channel, reason))
    conn.commit()

def get_temp_data(user_id):
    c.execute("SELECT scam_channel, scam_reason FROM temp_data WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    return res if res else (None, None)

def delete_temp_data(user_id):
    c.execute("DELETE FROM temp_data WHERE user_id = ?", (user_id,))
    conn.commit()

def init_users_db():
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
init_users_db()

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
    sub_date = datetime.strptime(sub, "%Y-%m-%d %H:%M:%S")
    return sub_date > datetime.now()

def set_sub(user_id, days):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    new_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR REPLACE INTO users (user_id, subscribe) VALUES (?, ?)", (user_id, new_date))
    conn.commit()
    conn.close()

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

def extract_channel_and_id(url):
    try:
        if 't.me/c/' in url:
            parts = url.split('/')
            return str(int('-100' + parts[4])), int(parts[5])
        else:
            path = url.split('t.me/')[-1].split('/')
            return path[0], int(path[1])
    except:
        return None, None

def extract_channel_only(url):
    try:
        return url.split('t.me/')[-1].split('/')[0].split('?')[0]
    except:
        return None

# ========== ОТПРАВКА ЖАЛОБ ==========
async def send_reports(chat_username, msg_id, user_id):
    ok = 0
    print(f"➡️ ЗАПУСК РЕПОРТА. СЕССИЙ: {len(sessions)}")
    if not sessions:
        bot.send_message(user_id, "❌ НЕТ СЕССИЙ! ПРОВЕРЬ SESSIONS_URL")
        return
    for ses in sessions:
        try:
            client = TelegramClient(os.path.join(session_folder, ses), config.API_ID, config.API_HASH, system_version='4.16.30-vxCUSTOM')
            await client.connect()
            if await client.is_user_authorized():
                chat = await client.get_entity(chat_username)
                reason = random.choice(list(reasons_map.values()))
                await client(ReportRequest(peer=chat, id=[msg_id], reason=reason, message=""))
                ok += 1
            await client.disconnect()
        except Exception as e:
            print(f"Ошибка сессии {ses}: {e}")
            continue
    bot.send_message(user_id, f"⚡️ РЕПОРТ\n✅ Успешно: {ok}\n❌ Ошибок: {len(sessions)-ok}")

async def send_scam_report(channel, reason, comment, user_id):
    ok = 0
    reason_map = {'finance': 'Ложные финансовые обещания', 'fake': 'Выдача себя за другое лицо', 'malware': 'Вредоносное ПО/фишинг', 'seller': 'Сомнительный продавец', 'other': 'Другое'}
    reason_text = reason_map.get(reason, 'Мошенничество')
    full_text = f"Reason: {reason_text}\nComment: {comment}" if comment else f"Reason: {reason_text}"
    print(f"➡️ ЗАПУСК SCAM РЕПОРТА. СЕССИЙ: {len(sessions)}")
    if not sessions:
        bot.send_message(user_id, "❌ НЕТ СЕССИЙ! ПРОВЕРЬ SESSIONS_URL")
        return
    for ses in sessions:
        try:
            client = TelegramClient(os.path.join(session_folder, ses), config.API_ID, config.API_HASH, system_version='4.16.30-vxCUSTOM')
            await client.connect()
            if await client.is_user_authorized():
                chat = await client.get_entity(channel)
                await client(ReportRequest(peer=chat, id=[], reason=InputReportReasonOther(), message=full_text))
                ok += 1
            await client.disconnect()
        except Exception as e:
            print(f"Ошибка сессии {ses}: {e}")
            continue
    bot.send_message(user_id, f"⚠️ SCAM РЕПОРТ\n✅ Успешно: {ok}\n❌ Ошибок: {len(sessions)-ok}")

# ========== ИНТЕРФЕЙС ==========
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data='profile'),
        types.InlineKeyboardButton("💰 ПОДПИСКА", callback_data='shop'),
        types.InlineKeyboardButton("⚡️ РЕПОРТ", callback_data='snoser'),
        types.InlineKeyboardButton("⚠️ SCAM", callback_data='scam_report')
    )
    return markup

def admin_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ ВЫДАТЬ", callback_data='add_subsribe'),
        types.InlineKeyboardButton("❌ ЗАБРАТЬ", callback_data='clear_subscribe'),
        types.InlineKeyboardButton("📢 РАССЫЛКА", callback_data='send_all'),
        types.InlineKeyboardButton("🎫 ПРОМОКОД", callback_data='add_promo'),
        types.InlineKeyboardButton("📋 СПИСОК", callback_data='view_promos')
    )
    return markup

def back_button():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ НАЗАД", callback_data='back'))
    return markup

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.chat.id
    check_user(uid)
    bot.send_message(uid, "🔥 БОТ АКТИВИРОВАН\nВыбери действие 👇", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    uid = call.from_user.id
    check_user(uid)

    if call.data == 'back':
        bot.edit_message_text("🔥 ГЛАВНОЕ МЕНЮ", call.message.chat.id, call.message.message_id, reply_markup=main_menu())
    elif call.data == 'profile':
        sub = get_sub_status(uid) or "Нет"
        bot.edit_message_text(f"📊 ПРОФИЛЬ\n\n🆔 ID: {uid}\n⏳ ПОДПИСКА: {sub}", call.message.chat.id, call.message.message_id, reply_markup=back_button())
    elif call.data == 'shop':
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("1 ДЕНЬ - 1$", callback_data='sub_1'),
            types.InlineKeyboardButton("7 ДНЕЙ - 3$", callback_data='sub_2'),
            types.InlineKeyboardButton("30 ДНЕЙ - 6$", callback_data='sub_3'),
            types.InlineKeyboardButton("♾ НАВСЕГДА - 12$", callback_data='sub_4'),
            types.InlineKeyboardButton("◀️ НАЗАД", callback_data='back')
        )
        bot.edit_message_text("💸 ВЫБЕРИ ПОДПИСКУ", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data.startswith('sub_'):
        typ = call.data.split('_')[1]
        prices = {'1': (1, '1'), '2': (3, '7'), '3': (6, '30'), '4': (12, '9999')}
        amount, days = prices.get(typ, (1, '1'))
        inv = crypto.create_invoice('USDT', amount)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💸 ОПЛАТИТЬ", url=inv['pay_url']))
        markup.add(types.InlineKeyboardButton("✅ ПРОВЕРИТЬ", callback_data=f"check_{inv['invoice_id']}_{days}"))
        markup.add(types.InlineKeyboardButton("◀️ НАЗАД", callback_data='shop'))
        bot.edit_message_text(f"💸 ОПЛАТА | {days} дней / {amount}$", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data.startswith('check_'):
        _, inv_id, days = call.data.split('_')
        try:
            inv = crypto.get_invoices(invoice_ids=inv_id)
            if inv['items'][0]['status'] == 'paid':
                set_sub(uid, int(days) if days != '9999' else 9999)
                bot.send_message(uid, "✅ ОПЛАЧЕНО!")
                bot.edit_message_text("✅ ГОТОВО", call.message.chat.id, call.message.message_id, reply_markup=main_menu())
            else:
                bot.answer_callback_query(call.id, "⏳ ЕЩЁ НЕ ОПЛАЧЕНО", show_alert=True)
        except:
            bot.answer_callback_query(call.id, "❌ ОШИБКА", show_alert=True)
    elif call.data == 'snoser':
        if not has_sub(uid):
            bot.send_message(uid, "❌ НЕТ ПОДПИСКИ", reply_markup=main_menu())
            return
        m = bot.send_message(uid, "🔗 ВВЕДИ ССЫЛКУ НА СООБЩЕНИЕ")
        bot.register_next_step_handler(m, lambda msg: asyncio.run(send_reports(*extract_channel_and_id(msg.text), uid)) if extract_channel_and_id(msg.text)[0] else bot.send_message(uid, "❌ НЕВЕРНАЯ ССЫЛКА"))
    elif call.data == 'scam_report':
        if not has_sub(uid):
            bot.send_message(uid, "❌ НЕТ ПОДПИСКИ", reply_markup=main_menu())
            return
        m = bot.send_message(uid, "🎭 ВВЕДИ ССЫЛКУ НА КАНАЛ")
        bot.register_next_step_handler(m, process_scam_channel, uid)
    elif call.data in ['scam_finance', 'scam_fake', 'scam_malware', 'scam_seller', 'scam_other']:
        reason = call.data.split('_')[1]
        channel, _ = get_temp_data(uid)
        if not channel:
            bot.send_message(uid, "❌ ОШИБКА, НАЧНИ ЗАНОВО")
            return
        save_temp_data(uid, channel, reason)
        m = bot.send_message(uid, "📝 КОММЕНТАРИЙ (или '-' пропустить)")
        bot.register_next_step_handler(m, process_scam_comment, uid)
    elif call.data in ['add_subsribe', 'clear_subscribe', 'send_all', 'add_promo', 'view_promos'] and uid in config.ADMINS:
        if call.data == 'add_subsribe':
            m = bot.send_message(uid, "➕ ВВЕДИ ID И ДНИ (через пробел)")
            bot.register_next_step_handler(m, add_sub2)
        elif call.data == 'clear_subscribe':
            m = bot.send_message(uid, "❌ ВВЕДИ ID")
            bot.register_next_step_handler(m, clear_sub2)
        elif call.data == 'send_all':
            m = bot.send_message(uid, "📢 ТЕКСТ РАССЫЛКИ")
            bot.register_next_step_handler(m, send_all_text)
        elif call.data == 'add_promo':
            m = bot.send_message(uid, "🎫 КОЛИЧЕСТВО ДНЕЙ")
            bot.register_next_step_handler(m, add_promo_days)
        elif call.data == 'view_promos':
            promos = get_promocodes()
            if not promos:
                bot.send_message(uid, "📋 НЕТ ПРОМОКОДОВ")
                return
            text = "📋 ПРОМОКОДЫ:\n\n"
            for code, days, used_by, _ in promos:
                status = "❌ ИСПОЛЬЗОВАН" if used_by else "✅ АКТИВЕН"
                text += f"`{code}` - {days} ДНЕЙ - {status}\n"
            bot.send_message(uid, text, parse_mode="Markdown")

def process_scam_channel(msg, uid):
    channel = extract_channel_only(msg.text)
    if not channel:
        bot.send_message(uid, "❌ НЕВЕРНАЯ ССЫЛКА")
        return
    save_temp_data(uid, channel, None)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💸 ЛОЖНЫЕ", callback_data="scam_finance"),
        types.InlineKeyboardButton("🎭 ВЫДАЧА", callback_data="scam_fake"),
        types.InlineKeyboardButton("💀 ФИШИНГ", callback_data="scam_malware"),
        types.InlineKeyboardButton("📦 ПРОДАВЕЦ", callback_data="scam_seller"),
        types.InlineKeyboardButton("🔄 ДРУГОЕ", callback_data="scam_other")
    )
    bot.send_message(uid, "🎭 ВЫБЕРИ ПРИЧИНУ", reply_markup=markup)

def process_scam_comment(msg, uid):
    comment = msg.text if msg.text != '-' else ''
    channel, reason = get_temp_data(uid)
    if not channel or not reason:
        bot.send_message(uid, "❌ ОШИБКА, НАЧНИ ЗАНОВО")
        return
    asyncio.run(send_scam_report(channel, reason, comment, uid))
    delete_temp_data(uid)

def add_sub2(msg):
    if msg.from_user.id not in config.ADMINS:
        return
    try:
        uid, days = map(int, msg.text.split())
        set_sub(uid, days)
        bot.send_message(msg.chat.id, f"✅ ВЫДАНО {days} ДНЕЙ")
        bot.send_message(uid, f"✅ АДМИН ВЫДАЛ {days} ДНЕЙ")
    except:
        bot.send_message(msg.chat.id, "❌ ОШИБКА")

def clear_sub2(msg):
    if msg.from_user.id not in config.ADMINS:
        return
    try:
        uid = int(msg.text)
        remove_sub(uid)
        bot.send_message(msg.chat.id, f"✅ ПОДПИСКА УДАЛЕНА")
        bot.send_message(uid, "❌ ПОДПИСКА УДАЛЕНА")
    except:
        bot.send_message(msg.chat.id, "❌ ОШИБКА")

def send_all_text(msg):
    if msg.from_user.id not in config.ADMINS:
        return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    users = c.execute("SELECT user_id FROM users").fetchall()
    ok = 0
    for u in users:
        try:
            bot.send_message(u[0], f"📢 РАССЫЛКА\n\n{msg.text}", parse_mode="Markdown")
            ok += 1
        except:
            pass
    bot.send_message(msg.chat.id, f"✅ ОТПРАВЛЕНО {ok}")
    conn.close()

def add_promo_days(msg):
    if msg.from_user.id not in config.ADMINS:
        return
    try:
        days = int(msg.text)
        code = create_promo_code(days, msg.from_user.id)
        bot.send_message(msg.chat.id, f"✅ ПРОМОКОД:\n`{code}`", parse_mode="Markdown")
    except:
        bot.send_message(msg.chat.id, "❌ ОШИБКА")

@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if msg.from_user.id in config.ADMINS:
        bot.send_message(msg.chat.id, "👑 АДМИН ПАНЕЛЬ", reply_markup=admin_menu())

if __name__ == '__main__':
    print("🚀 БОТ ЗАПУЩЕН")
    bot.infinity_polling()
