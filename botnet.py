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
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import (
    InputReportReasonSpam, InputReportReasonFake,
    InputReportReasonViolence, InputReportReasonChildAbuse,
    InputReportReasonOther
)
import telebot
from telebot import types
from pyCryptoPayAPI import pyCryptoPayAPI
import config

# ========== ПУТИ (ВСЁ В /app/data) ==========
DATA_DIR = '/app/data'
os.makedirs(DATA_DIR, exist_ok=True)
USERS_DB = os.path.join(DATA_DIR, 'users.db')
SESSION_FOLDER = os.path.join(DATA_DIR, 'sessions')
os.makedirs(SESSION_FOLDER, exist_ok=True)

# ========== АВТОЗАГРУЗКА СЕССИЙ ==========
if config.SESSIONS_URL:
    print("🔄 Загружаю сессии...", flush=True)
    try:
        if os.path.exists(SESSION_FOLDER):
            shutil.rmtree(SESSION_FOLDER)
        os.makedirs(SESSION_FOLDER, exist_ok=True)
        r = requests.get(config.SESSIONS_URL, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            zf.extractall(SESSION_FOLDER)
        print("✅ Сессии загружены", flush=True)
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}", flush=True)

sessions = [f.replace('.session', '') for f in os.listdir(SESSION_FOLDER) if f.endswith('.session')]
print(f"🔍 Найдено сессий: {len(sessions)}", flush=True)

# ========== SQLite ФУНКЦИИ ==========
def init_db():
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        subscribe TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS promocodes(
        code TEXT PRIMARY KEY,
        days INTEGER,
        created_by INTEGER,
        used_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована", flush=True)
init_db()

def get_sub(user_id):
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("SELECT subscribe FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def has_sub(user_id):
    sub = get_sub(user_id)
    if not sub or sub == 'None':
        return False
    try:
        return datetime.strptime(sub, "%Y-%m-%d %H:%M:%S") > datetime.now()
    except:
        return False

def set_sub(user_id, days):
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("SELECT subscribe FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row and row[0] and row[0] != 'None':
        try:
            old = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            new_date = max(old, datetime.now()) + timedelta(days=days)
        except:
            new_date = datetime.now() + timedelta(days=days)
    else:
        new_date = datetime.now() + timedelta(days=days)
    new_date_str = new_date.strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR REPLACE INTO users (user_id, subscribe) VALUES (?, ?)", (user_id, new_date_str))
    conn.commit()
    conn.close()

def remove_sub(user_id):
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("UPDATE users SET subscribe = 'None' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def create_promo(days, admin_id):
    code = secrets.token_hex(8).upper()
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("INSERT INTO promocodes (code, days, created_by) VALUES (?, ?, ?)", (code, days, admin_id))
    conn.commit()
    conn.close()
    return code

def use_promo(user_id, code):
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("SELECT days, used_by FROM promocodes WHERE code = ?", (code,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "❌ Промокод не найден"
    days, used_by = row
    if used_by:
        conn.close()
        return False, "❌ Промокод уже использован"
    set_sub(user_id, days)
    c.execute("UPDATE promocodes SET used_by = ? WHERE code = ?", (user_id, code))
    conn.commit()
    conn.close()
    return True, f"✅ Подписка активирована на {days} дней"

def get_promos():
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("SELECT code, days, used_by FROM promocodes ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows

# ========== ПРОКСИ ==========
def get_proxy_config():
    if not config.USE_PROXY or not config.PROXY:
        return None
    proxy_str = config.PROXY
    if proxy_str.startswith('socks5://'):
        proxy_str = proxy_str[9:]
    if '@' in proxy_str:
        auth, addr = proxy_str.split('@')
        login, password = auth.split(':')
        host, port = addr.split(':')
        return ('socks5', host, int(port), True, login, password)
    else:
        host, port = proxy_str.split(':')
        return ('socks5', host, int(port), True, None, None)

# ========== ПРИЧИНЫ ЖАЛОБ ==========
reasons_map = {
    "spam": InputReportReasonSpam(),
    "fake": InputReportReasonFake(),
    "violence": InputReportReasonViolence(),
    "child": InputReportReasonChildAbuse(),
    "other": InputReportReasonOther()
}

# ========== БОТ ==========
bot = telebot.TeleBot(config.TOKEN)
crypto = pyCryptoPayAPI(api_token=config.CRYPTO)
last_used = {}

# ========== КЛАВИАТУРЫ ==========
def main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data='profile'),
        types.InlineKeyboardButton("💸 ПОДПИСКА", callback_data='shop'),
        types.InlineKeyboardButton("⚡️ РЕПОРТ", callback_data='snoser'),
        types.InlineKeyboardButton("⚠️ SCAM (канал)", callback_data='scam_channel')
    )
    return m

def back_btn():
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("◀️ НАЗАД", callback_data='back'))
    return m

def admin_btns():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("➕ ВЫДАТЬ", callback_data='add_sub'),
        types.InlineKeyboardButton("❌ ЗАБРАТЬ", callback_data='remove_sub'),
        types.InlineKeyboardButton("📢 РАССЫЛКА", callback_data='send_all'),
        types.InlineKeyboardButton("🎫 ПРОМОКОД", callback_data='promo_create'),
        types.InlineKeyboardButton("📋 СПИСОК", callback_data='promo_list')
    )
    return m

def shop_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton(f"1 ДЕНЬ - {config.PRICE_1_DAY}$", callback_data='sub_1'),
        types.InlineKeyboardButton(f"7 ДНЕЙ - {config.PRICE_7_DAYS}$", callback_data='sub_2'),
        types.InlineKeyboardButton(f"30 ДНЕЙ - {config.PRICE_30_DAYS}$", callback_data='sub_3'),
        types.InlineKeyboardButton(f"♾ НАВСЕГДА - {config.PRICE_INFINITY}$", callback_data='sub_4'),
        types.InlineKeyboardButton("◀️ НАЗАД", callback_data='back')
    )
    return m

# ========== ФУНКЦИИ ОТПРАВКИ ЖАЛОБ ==========
async def send_report(chat_username, message_id, user_id, is_channel=False, custom_text=""):
    api_id = config.API_ID
    api_hash = config.API_HASH
    proxy = get_proxy_config()
    valid = 0
    ne_valid = 0
    flood = 0
    
    for session in sessions:
        reason = random.choice(list(reasons_map.values()))
        try:
            client = TelegramClient(
                os.path.join(SESSION_FOLDER, session),
                api_id, api_hash,
                proxy=proxy,
                system_version='4.16.30-vxCUSTOM'
            )
            await client.connect()
            if not await client.is_user_authorized():
                ne_valid += 1
                await client.disconnect()
                continue
            
            entity = await client.get_entity(chat_username)
            if is_channel:
                await client(ReportRequest(peer=entity, id=[], reason=reason, message=custom_text))
            else:
                await client(ReportRequest(peer=entity, id=[message_id], reason=reason, message=custom_text or "Сообщение содержит спам"))
            
            valid += 1
            await asyncio.sleep(random.uniform(config.REPORT_DELAY_MIN, config.REPORT_DELAY_MAX))
            await client.disconnect()
            
        except FloodWaitError as e:
            flood += 1
            await asyncio.sleep(e.seconds)
        except Exception:
            ne_valid += 1
    
    bot.send_message(user_id,
        f"{'⚠️ SCAM КАНАЛ' if is_channel else '⚡️ РЕПОРТ'}\n\n"
        f"✅ Успешно: {valid}\n"
        f"❌ Ошибок: {ne_valid}\n"
        f"⏱ FloodWait: {flood}",
        reply_markup=main_menu())

# ========== ХЕНДЛЕРЫ ==========
@bot.message_handler(commands=['start'])
def start(m):
    uid = m.chat.id
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, subscribe) VALUES (?, 'None')", (uid,))
    conn.commit()
    conn.close()
    bot.send_message(uid, "🔥 *БОТ АКТИВИРОВАН*\nВыбери действие 👇", reply_markup=main_menu(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda c: True)
def handle(call):
    uid = call.from_user.id
    
    if call.data == 'back':
        bot.edit_message_text("🔥 *ГЛАВНОЕ МЕНЮ*", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode='Markdown')
    
    elif call.data == 'profile':
        sub = get_sub(uid) or 'Нет'
        bot.edit_message_text(f"📊 *ПРОФИЛЬ*\n🆔 ID: `{uid}`\n⏳ ПОДПИСКА: `{sub}`", call.message.chat.id, call.message.message_id, reply_markup=back_btn(), parse_mode='Markdown')
    
    elif call.data == 'shop':
        bot.edit_message_text("💸 *ВЫБЕРИ ПОДПИСКУ*", call.message.chat.id, call.message.message_id, reply_markup=shop_menu(), parse_mode='Markdown')
    
    elif call.data.startswith('sub_'):
        typ = call.data.split('_')[1]
        price_map = {'1': (config.PRICE_1_DAY, 1), '2': (config.PRICE_7_DAYS, 7), '3': (config.PRICE_30_DAYS, 30), '4': (config.PRICE_INFINITY, 9999)}
        amount, days = price_map.get(typ, (1, 1))
        inv = crypto.create_invoice('USDT', amount)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💸 ОПЛАТИТЬ", url=inv['pay_url']))
        markup.add(types.InlineKeyboardButton("✅ ПРОВЕРИТЬ", callback_data=f"check_{inv['invoice_id']}_{days}"))
        markup.add(types.InlineKeyboardButton("◀️ НАЗАД", callback_data='shop'))
        bot.edit_message_text(f"💸 *ОПЛАТА {days} дней | {amount}$*", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
    
    elif call.data.startswith('check_'):
        _, inv_id, days = call.data.split('_')
        try:
            inv = crypto.get_invoices(invoice_ids=inv_id)
            if inv['items'][0]['status'] == 'paid':
                set_sub(uid, int(days) if days != '9999' else 9999)
                bot.send_message(uid, "✅ *ОПЛАЧЕНО!* Подписка активна", parse_mode='Markdown')
                bot.edit_message_text("✅ *ГОТОВО*", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode='Markdown')
            else:
                bot.answer_callback_query(call.id, "⏳ Ещё не оплачено", show_alert=True)
        except:
            bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=True)
    
    elif call.data == 'snoser':
        if not has_sub(uid):
            bot.send_message(uid, "❌ *НЕТ ПОДПИСКИ*", reply_markup=main_menu(), parse_mode='Markdown')
            return
        if uid in last_used and (datetime.now() - last_used[uid]) < timedelta(minutes=5):
            rem = timedelta(minutes=5) - (datetime.now() - last_used[uid])
            bot.edit_message_text(f"❌ *ЖДИ {rem.seconds//60}:{rem.seconds%60}*", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode='Markdown')
            return
        last_used[uid] = datetime.now()
        m = bot.send_message(uid, "🔗 *ВВЕДИ ССЫЛКУ НА СООБЩЕНИЕ*\nПример: https://t.me/username/123", parse_mode='Markdown')
        bot.register_next_step_handler(m, lambda msg: asyncio.run(send_report(msg.text.split('t.me/')[-1].split('/')[0], int(msg.text.split('/')[-1]), uid)))
    
    elif call.data == 'scam_channel':
        if not has_sub(uid):
            bot.send_message(uid, "❌ *НЕТ ПОДПИСКИ*", reply_markup=main_menu(), parse_mode='Markdown')
            return
        m = bot.send_message(uid, "🔗 *ВВЕДИ ССЫЛКУ НА КАНАЛ*\nПример: t.me/durov", parse_mode='Markdown')
        bot.register_next_step_handler(m, lambda msg: asyncio.run(send_report(msg.text.strip().replace('https://t.me/', '').replace('@', ''), None, uid, is_channel=True, custom_text=config.SCAM_TEXT)))
    
    # Админ команды
    elif uid in config.ADMINS:
        if call.data == 'add_sub':
            m = bot.send_message(uid, "➕ *ID И ДНИ (через пробел)*", parse_mode='Markdown')
            bot.register_next_step_handler(m, add_sub_cmd)
        elif call.data == 'remove_sub':
            m = bot.send_message(uid, "❌ *ВВЕДИ ID*", parse_mode='Markdown')
            bot.register_next_step_handler(m, rem_sub_cmd)
        elif call.data == 'send_all':
            m = bot.send_message(uid, "📢 *ТЕКСТ РАССЫЛКИ*", parse_mode='Markdown')
            bot.register_next_step_handler(m, send_all_cmd)
        elif call.data == 'promo_create':
            m = bot.send_message(uid, "🎫 *КОЛИЧЕСТВО ДНЕЙ*", parse_mode='Markdown')
            bot.register_next_step_handler(m, create_promo_cmd)
        elif call.data == 'promo_list':
            promos = get_promos()
            if not promos:
                bot.send_message(uid, "📋 *НЕТ ПРОМОКОДОВ*", parse_mode='Markdown')
                return
            text = "📋 *ПРОМОКОДЫ:*\n\n"
            for code, days, used in promos:
                status = "❌ ИСПОЛЬЗОВАН" if used else "✅ АКТИВЕН"
                text += f"`{code}` - {days} ДНЕЙ - {status}\n"
            bot.send_message(uid, text, parse_mode='Markdown')

# ========== АДМИН ФУНКЦИИ ==========
def add_sub_cmd(m):
    if m.from_user.id not in config.ADMINS:
        return
    try:
        uid, days = map(int, m.text.split())
        set_sub(uid, days)
        bot.send_message(m.chat.id, f"✅ *ВЫДАНО {days} ДНЕЙ*", parse_mode='Markdown')
        bot.send_message(uid, f"✅ *АДМИН ВЫДАЛ {days} ДНЕЙ*", parse_mode='Markdown')
    except:
        bot.send_message(m.chat.id, "❌ *ОШИБКА*", parse_mode='Markdown')

def rem_sub_cmd(m):
    if m.from_user.id not in config.ADMINS:
        return
    try:
        uid = int(m.text)
        remove_sub(uid)
        bot.send_message(m.chat.id, f"✅ *ПОДПИСКА УДАЛЕНА*", parse_mode='Markdown')
        bot.send_message(uid, "❌ *ПОДПИСКА УДАЛЕНА*", parse_mode='Markdown')
    except:
        bot.send_message(m.chat.id, "❌ *ОШИБКА*", parse_mode='Markdown')

def send_all_cmd(m):
    if m.from_user.id not in config.ADMINS:
        return
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    users = c.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    ok = 0
    for user in users:
        try:
            bot.send_message(user[0], f"📢 *РАССЫЛКА*\n\n{m.text}", parse_mode='Markdown')
            ok += 1
        except:
            pass
    bot.send_message(m.chat.id, f"✅ *ОТПРАВЛЕНО {ok}*", parse_mode='Markdown')

def create_promo_cmd(m):
    if m.from_user.id not in config.ADMINS:
        return
    try:
        days = int(m.text)
        code = create_promo(days, m.from_user.id)
        bot.send_message(m.chat.id, f"✅ *ПРОМОКОД:*\n`{code}`", parse_mode='Markdown')
    except:
        bot.send_message(m.chat.id, "❌ *ОШИБКА*", parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def admin_panel(m):
    if m.from_user.id in config.ADMINS:
        bot.send_message(m.chat.id, "👑 *АДМИН ПАНЕЛЬ*", reply_markup=admin_btns(), parse_mode='Markdown')
    else:
        bot.send_message(m.chat.id, "❌ *НЕТ ДОСТУПА*", parse_mode='Markdown')

if __name__ == '__main__':
    print("🚀 БОТ ЗАПУЩЕН", flush=True)
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
