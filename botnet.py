import os
import random
import asyncio
import zipfile
import requests
import io
import secrets
import shutil
import json
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import InputReportReasonSpam, InputReportReasonFake, InputReportReasonViolence, InputReportReasonChildAbuse, InputReportReasonOther
import telebot
from telebot import types
from pyCryptoPayAPI import pyCryptoPayAPI
import config
import firebase_admin
from firebase_admin import credentials, firestore

# ========== FIREBASE ==========
FIREBASE_JSON = os.getenv('FIREBASE_JSON')
if not FIREBASE_JSON:
    raise Exception("❌ Нет переменной FIREBASE_JSON!")
cred_dict = json.loads(FIREBASE_JSON)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

# ========== ЗАГРУЗКА СЕССИЙ ==========
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

session_folder = config.SESSION_FOLDER
os.makedirs(session_folder, exist_ok=True)
sessions = [f.replace('.session', '') for f in os.listdir(session_folder) if f.endswith('.session')]
print(f"🔍 Найдено сессий: {len(sessions)}")

# ========== BOT ==========
bot = telebot.TeleBot(config.TOKEN)
crypto = pyCryptoPayAPI(api_token=config.CRYPTO)

reasons_map = {
    "spam": InputReportReasonSpam(),
    "fake": InputReportReasonFake(),
    "violence": InputReportReasonViolence(),
    "child": InputReportReasonChildAbuse(),
    "other": InputReportReasonOther()
}

# ========== FIREBASE ФУНКЦИИ ==========
def get_sub(user_id):
    doc = db.collection('users').document(str(user_id)).get()
    return doc.to_dict().get('subscribe') if doc.exists else None

def has_sub(user_id):
    sub = get_sub(user_id)
    if not sub or sub == 'None':
        return False
    try:
        return datetime.strptime(sub, "%Y-%m-%d %H:%M:%S") > datetime.now()
    except:
        return False

def set_sub(user_id, days):
    current = get_sub(user_id)
    if current and current != 'None':
        try:
            old = datetime.strptime(current, "%Y-%m-%d %H:%M:%S")
            new_date = max(old, datetime.now()) + timedelta(days=days)
        except:
            new_date = datetime.now() + timedelta(days=days)
    else:
        new_date = datetime.now() + timedelta(days=days)
    new_date_str = new_date.strftime("%Y-%m-%d %H:%M:%S")
    db.collection('users').document(str(user_id)).set({'subscribe': new_date_str}, merge=True)
    return new_date_str

def remove_sub(user_id):
    db.collection('users').document(str(user_id)).set({'subscribe': 'None'}, merge=True)

def create_promo(days, admin_id):
    code = secrets.token_hex(8).upper()
    db.collection('promocodes').document(code).set({
        'days': days,
        'used_by': None,
        'created_by': admin_id,
        'created_at': firestore.SERVER_TIMESTAMP
    })
    return code

def use_promo(user_id, code):
    doc = db.collection('promocodes').document(code.upper()).get()
    if not doc.exists:
        return False, "❌ Промокод не найден"
    data = doc.to_dict()
    if data.get('used_by'):
        return False, "❌ Промокод уже использован"
    set_sub(user_id, data['days'])
    db.collection('promocodes').document(code.upper()).update({
        'used_by': user_id,
        'used_at': firestore.SERVER_TIMESTAMP
    })
    return True, f"✅ Подписка активирована на {data['days']} дней"

def get_promos():
    docs = db.collection('promocodes').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
    return [(d.id, d.to_dict().get('days'), d.to_dict().get('used_by')) for d in docs]

# ========== ВИЗУАЛ ==========
def main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data='profile'),
        types.InlineKeyboardButton("💸 ПОДПИСКА", callback_data='shop'),
        types.InlineKeyboardButton("⚡️ РЕПОРТ", callback_data='snoser'),
        types.InlineKeyboardButton("⚠️ SCAM", callback_data='scam_report')
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

# ========== ОТПРАВКА ==========
async def send_report(chat, msg_id, user_id):
    ok = 0
    for ses in sessions:
        try:
            client = TelegramClient(os.path.join(session_folder, ses), config.API_ID, config.API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                entity = await client.get_entity(chat)
                reason = random.choice(list(reasons_map.values()))
                await client(ReportRequest(peer=entity, id=[msg_id], reason=reason, message=""))
                ok += 1
            await client.disconnect()
        except:
            continue
    bot.send_message(user_id, f"⚡️ РЕПОРТ\n✅ {ok}\n❌ {len(sessions)-ok}")

async def send_scam(channel, reason, comment, user_id):
    ok = 0
    reasons = {
        'finance': 'Ложные финансовые обещания',
        'fake': 'Выдача себя за другое лицо',
        'malware': 'Вредоносное ПО/фишинг',
        'seller': 'Сомнительный продавец',
        'other': 'Другое'
    }
    text = reasons.get(reason, 'Мошенничество')
    if comment:
        text += f"\nComment: {comment}"
    for ses in sessions:
        try:
            client = TelegramClient(os.path.join(session_folder, ses), config.API_ID, config.API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                entity = await client.get_entity(channel)
                await client(ReportRequest(peer=entity, id=[], reason=InputReportReasonOther(), message=text))
                ok += 1
            await client.disconnect()
        except:
            continue
    bot.send_message(user_id, f"⚠️ SCAM\n✅ {ok}\n❌ {len(sessions)-ok}")

# ========== ХЭНДЛЕРЫ ==========
@bot.message_handler(commands=['start'])
def start(m):
    db.collection('users').document(str(m.chat.id)).set({}, merge=True)
    bot.send_message(m.chat.id, "🔥 *БОТ АКТИВИРОВАН*\nВыбери действие 👇", reply_markup=main_menu(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda c: True)
def handle(call):
    uid = call.from_user.id
    if call.data == 'back':
        bot.edit_message_text("🔥 *ГЛАВНОЕ МЕНЮ*", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode='Markdown')
    elif call.data == 'profile':
        sub = get_sub(uid) or 'Нет'
        bot.edit_message_text(f"📊 *ПРОФИЛЬ*\n🆔 ID: `{uid}`\n⏳ ПОДПИСКА: `{sub}`", call.message.chat.id, call.message.message_id, reply_markup=back_btn(), parse_mode='Markdown')
    elif call.data == 'shop':
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(
            types.InlineKeyboardButton("1 ДЕНЬ - 1$", callback_data='sub_1'),
            types.InlineKeyboardButton("7 ДНЕЙ - 3$", callback_data='sub_2'),
            types.InlineKeyboardButton("30 ДНЕЙ - 6$", callback_data='sub_3'),
            types.InlineKeyboardButton("♾ НАВСЕГДА - 12$", callback_data='sub_4'),
            types.InlineKeyboardButton("◀️ НАЗАД", callback_data='back')
        )
        bot.edit_message_text("💸 *ВЫБЕРИ ПОДПИСКУ*", call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode='Markdown')
    elif call.data.startswith('sub_'):
        typ = call.data.split('_')[1]
        price_map = {'1': (1, '1'), '2': (3, '7'), '3': (6, '30'), '4': (12, '9999')}
        amount, days = price_map.get(typ, (1, '1'))
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
        m = bot.send_message(uid, "🔗 *ВВЕДИ ССЫЛКУ НА СООБЩЕНИЕ*", parse_mode='Markdown')
        bot.register_next_step_handler(m, lambda msg: process_report(msg, uid))
    elif call.data == 'scam_report':
        if not has_sub(uid):
            bot.send_message(uid, "❌ *НЕТ ПОДПИСКИ*", reply_markup=main_menu(), parse_mode='Markdown')
            return
        m = bot.send_message(uid, "🎭 *ВВЕДИ ССЫЛКУ НА КАНАЛ*", parse_mode='Markdown')
        bot.register_next_step_handler(m, lambda msg: process_scam_channel(msg, uid))
    elif call.data in ['add_sub', 'remove_sub', 'send_all', 'promo_create', 'promo_list'] and uid in config.ADMINS:
        if call.data == 'add_sub':
            m = bot.send_message(uid, "➕ *ID И ДНИ (через пробел)*", parse_mode='Markdown')
            bot.register_next_step_handler(m, add_sub)
        elif call.data == 'remove_sub':
            m = bot.send_message(uid, "❌ *ВВЕДИ ID*", parse_mode='Markdown')
            bot.register_next_step_handler(m, rem_sub)
        elif call.data == 'send_all':
            m = bot.send_message(uid, "📢 *ТЕКСТ РАССЫЛКИ*", parse_mode='Markdown')
            bot.register_next_step_handler(m, send_all)
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
    elif call.data.startswith('scam_reason_'):
        reason = call.data.split('_')[2]
        channel = temp_data.get(uid, {}).get('channel')
        if not channel:
            bot.send_message(uid, "❌ *ОШИБКА, НАЧНИ ЗАНОВО*", parse_mode='Markdown')
            return
        temp_data[uid]['reason'] = reason
        m = bot.send_message(uid, "📝 *КОММЕНТАРИЙ (или '-' пропустить)*", parse_mode='Markdown')
        bot.register_next_step_handler(m, lambda msg: scam_comment(msg, uid))

temp_data = {}

def process_report(msg, uid):
    url = msg.text
    try:
        if 't.me/c/' in url:
            parts = url.split('/')
            chat = str(int('-100' + parts[4]))
            mid = int(parts[5])
        else:
            path = url.split('t.me/')[-1].split('/')
            chat = path[0]
            mid = int(path[1])
        asyncio.run(send_report(chat, mid, uid))
    except:
        bot.send_message(uid, "❌ *НЕВЕРНАЯ ССЫЛКА*", parse_mode='Markdown')

def process_scam_channel(msg, uid):
    url = msg.text
    try:
        channel = url.split('t.me/')[-1].split('/')[0].split('?')[0]
        temp_data[uid] = {'channel': channel}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("💸 ЛОЖНЫЕ", callback_data='scam_reason_finance'),
            types.InlineKeyboardButton("🎭 ВЫДАЧА", callback_data='scam_reason_fake'),
            types.InlineKeyboardButton("💀 ФИШИНГ", callback_data='scam_reason_malware'),
            types.InlineKeyboardButton("📦 ПРОДАВЕЦ", callback_data='scam_reason_seller'),
            types.InlineKeyboardButton("🔄 ДРУГОЕ", callback_data='scam_reason_other')
        )
        bot.send_message(uid, "🎭 *ВЫБЕРИ ПРИЧИНУ*", reply_markup=markup, parse_mode='Markdown')
    except:
        bot.send_message(uid, "❌ *НЕВЕРНАЯ ССЫЛКА*", parse_mode='Markdown')

def scam_comment(msg, uid):
    comment = msg.text if msg.text != '-' else ''
    data = temp_data.get(uid, {})
    if not data.get('channel') or not data.get('reason'):
        bot.send_message(uid, "❌ *ОШИБКА, НАЧНИ ЗАНОВО*", parse_mode='Markdown')
        return
    asyncio.run(send_scam(data['channel'], data['reason'], comment, uid))
    del temp_data[uid]

# ========== АДМИН ФУНКЦИИ ==========
def add_sub(m):
    if m.from_user.id not in config.ADMINS:
        return
    try:
        uid, days = map(int, m.text.split())
        set_sub(uid, days)
        bot.send_message(m.chat.id, f"✅ *ВЫДАНО {days} ДНЕЙ*", parse_mode='Markdown')
        bot.send_message(uid, f"✅ *АДМИН ВЫДАЛ {days} ДНЕЙ*", parse_mode='Markdown')
    except:
        bot.send_message(m.chat.id, "❌ *ОШИБКА*", parse_mode='Markdown')

def rem_sub(m):
    if m.from_user.id not in config.ADMINS:
        return
    try:
        uid = int(m.text)
        remove_sub(uid)
        bot.send_message(m.chat.id, f"✅ *ПОДПИСКА УДАЛЕНА*", parse_mode='Markdown')
        bot.send_message(uid, "❌ *ПОДПИСКА УДАЛЕНА*", parse_mode='Markdown')
    except:
        bot.send_message(m.chat.id, "❌ *ОШИБКА*", parse_mode='Markdown')

def send_all(m):
    if m.from_user.id not in config.ADMINS:
        return
    users = db.collection('users').stream()
    ok = 0
    for user in users:
        try:
            bot.send_message(int(user.id), f"📢 *РАССЫЛКА*\n\n{m.text}", parse_mode='Markdown')
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

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    print("🚀 БОТ ЗАПУЩЕН НА FIREBASE")
    bot.infinity_polling()
