import sqlite3
import telethon
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.functions.messages import ReportRequest
import asyncio
import telebot
from telebot import types
from telethon import types as telethon_types
import time
import os
import shutil
import random
from datetime import datetime, timedelta
from pyCryptoPayAPI import pyCryptoPayAPI
import config
from telethon.tl.types import PeerUser

# ========== ПРОКСИ МЕНЕДЖЕР ==========
class ProxyManager:
    def __init__(self, proxy_file='proxy.txt'):
        self.proxies = self._load_proxies(proxy_file)
        self.assigned = {}
    
    def _load_proxies(self, proxy_file):
        if not os.path.exists(proxy_file):
            return []
        proxies = []
        with open(proxy_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    parts = line.split(':')
                    if len(parts) == 4:  # ip:port:login:pass
                        host, port, login, password = parts
                        proxies.append(('socks5', host, int(port), True, login, password))
                    elif len(parts) == 2:  # ip:port
                        host, port = parts
                        proxies.append(('socks5', host, int(port), True, None, None))
        return proxies
    
    def get_proxy(self, session_name):
        if not self.proxies:
            return None
        if session_name not in self.assigned:
            self.assigned[session_name] = random.choice(self.proxies)
        return self.assigned[session_name]

# ========== ОСНОВНОЙ КОД ==========
while True:
    try:
        reasons = [
            telethon_types.InputReportReasonSpam(),
            telethon_types.InputReportReasonViolence(),
            telethon_types.InputReportReasonPornography(),
            telethon_types.InputReportReasonChildAbuse(),
            telethon_types.InputReportReasonIllegalDrugs(),
            telethon_types.InputReportReasonPersonalDetails(),
        ]

        API = config.API  # "api_id:api_hash" в config.py
        bot = telebot.TeleBot(config.TOKEN)
        bot_name = config.bot_name
        bot_logs = config.bot_logs
        bot_channel_link = config.bot_channel_link
        bot_admin = config.bot_admin
        bot_documentation = config.bot_documentation
        bot_reviews = config.bot_reviews
        bot_works = config.bot_works
        bot_channel = config.bot_channel
        bot_information = config.bot_information
        crypto = pyCryptoPayAPI(api_token=config.CRYPTO)
        session_folder = 'sessions'
        sessions = [f.replace('.session', '') for f in os.listdir(session_folder) if f.endswith('.session')]
        last_used = {}

        subscribe_1_day = config.subscribe_1_day
        subscribe_7_days = config.subscribe_7_days
        subscribe_14_days = config.subscribe_14_days
        subscribe_30_days = config.subscribe_30_days
        subscribe_365_days = config.subscribe_365_days
        subscribe_infinity_days = config.subscribe_infinity_days

        # Инициализация прокси
        proxy_manager = ProxyManager('proxy.txt') if config.USE_PROXY else None

        # ========== КЛАВИАТУРЫ ==========
        menu = types.InlineKeyboardMarkup(row_width=2)
        profile = types.InlineKeyboardButton("👤 Профиль", callback_data='profile')
        channel = types.InlineKeyboardButton("📢 Канал", url=f'{bot_channel}')
        information = types.InlineKeyboardButton("ℹ️ Информация", url=f'{bot_information}')
        shop = types.InlineKeyboardButton("💸 Подписка", callback_data='shop')
        snoser = types.InlineKeyboardButton("⚡️ РЕПОРТ", callback_data='snoser')
        scam = types.InlineKeyboardButton("⚠️ SCAM (канал)", callback_data='scam_channel')
        menu.add(snoser, scam)
        menu.add(channel, information)
        menu.add(profile, shop)

        back_markup = types.InlineKeyboardMarkup(row_width=2)
        back = types.InlineKeyboardButton("◀️ Назад", callback_data='back')
        back_markup.add(back)

        channel_markup = types.InlineKeyboardMarkup(row_width=2)
        channel_btn = types.InlineKeyboardButton(f"📢 Подпишись", url=f'{bot_channel_link}')
        channel_markup.add(channel_btn)

        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        add_subsribe = types.InlineKeyboardButton("➕ Выдать", callback_data='add_subsribe')
        clear_subscribe = types.InlineKeyboardButton("❌ Забрать", callback_data='clear_subscribe')
        send_all = types.InlineKeyboardButton("📢 Рассылка", callback_data='send_all')
        admin_markup.add(add_subsribe, clear_subscribe)
        admin_markup.add(send_all)

        shop_markup = types.InlineKeyboardMarkup(row_width=2)
        sub_1 = types.InlineKeyboardButton(f"1 день - {subscribe_1_day}$", callback_data='sub_1')
        sub_2 = types.InlineKeyboardButton(f"7 дней - {subscribe_7_days}$", callback_data='sub_2')
        sub_4 = types.InlineKeyboardButton(f"30 дней - {subscribe_30_days}$", callback_data='sub_4')
        sub_6 = types.InlineKeyboardButton(f"Навсегда - {subscribe_infinity_days}$", callback_data='sub_6')
        shop_markup.add(sub_1, sub_2)
        shop_markup.add(sub_4, sub_6)
        shop_markup.add(back)

        # ========== ФУНКЦИИ ==========
        def check_user_in_db(user_id):
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result is not None

        def extract_username_and_message_id(message_url):
            path = message_url[len('https://t.me/'):].split('/')
            if len(path) == 2:
                chat_username = path[0]
                message_id = int(path[1])
                return chat_username, message_id
            raise ValueError("Неверная ссылка!")

        async def main_reports(chat_username, message_id, user, is_channel=False, custom_text=""):
            connect = sqlite3.connect('users.db')
            cursor = connect.cursor()
            valid = 0
            ne_valid = 0
            flood = 0
            api_id, api_hash = API.split(":")
            
            for session in sessions:
                proxy = proxy_manager.get_proxy(session) if proxy_manager else None
                random_reason = random.choice(reasons)
                try:
                    client = TelegramClient(
                        "./sessions/" + session, 
                        int(api_id), 
                        api_hash, 
                        proxy=proxy,
                        system_version='4.16.30-vxCUSTOM'
                    )
                    await client.connect()
                    if not await client.is_user_authorized():
                        print(f"Сессия {session} не валид.")
                        ne_valid += 1
                        await client.disconnect()
                        continue

                    await client.start()
                    
                    if is_channel:
                        entity = await client.get_entity(chat_username)
                        await client(ReportRequest(
                            peer=entity,
                            id=[],
                            reason=random_reason,
                            message=custom_text
                        ))
                    else:
                        chat = await client.get_entity(chat_username)
                        await client(ReportRequest(
                            peer=chat,
                            id=[message_id],
                            reason=random_reason,
                            message=custom_text if custom_text else "Сообщение содержит спам."
                        ))
                    
                    valid += 1
                    await asyncio.sleep(random.uniform(3, 8))
                    await client.disconnect()
                    
                except FloodWaitError as e:
                    flood += 1
                    print(f'Flood wait ({session}): {e}')
                    await asyncio.sleep(e.seconds)
                    await client.disconnect()
                except Exception as e:
                    ne_valid += 1
                    print(f'Ошибка ({session}): {e}')
                    await client.disconnect()
                    continue
            
            bot.send_message(user, 
                f"*{'SCAM КАНАЛ' if is_channel else 'РЕПОРТ'}*\n\n"
                f"✅ *Успешно:* `{valid}`\n"
                f"❌ *Ошибок:* `{ne_valid}`\n"
                f"⏱ *FloodWait:* `{flood}`",
                parse_mode="Markdown", reply_markup=back_markup)
            connect.close()

        # ========== ХЕНДЛЕРЫ БОТА ==========
        @bot.message_handler(commands=['start'])
        def welcome(message):
            connect = sqlite3.connect("users.db")
            cursor = connect.cursor()
            cursor.execute("""CREATE TABLE IF NOT EXISTS users(
                user_id BIGINT,
                subscribe DATETIME
            )""")
            people_id = message.chat.id
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (people_id,))
            data = cursor.fetchone()
            if data is None:
                cursor.execute("INSERT INTO users VALUES(?, ?);", (people_id, "1999-01-01 20:00:00"))
                connect.commit()
                bot.send_message(message.chat.id, "👋 *Привет!*\nПодпишись на канал чтобы продолжить", reply_markup=channel_markup, parse_mode="Markdown")
            bot.send_message(message.chat.id, f'⚡️ *ГЛАВНОЕ МЕНЮ* ⚡️', parse_mode="Markdown", reply_markup=menu)
            connect.close()

        @bot.callback_query_handler(lambda c: c.data and c.data.startswith('sub_'))
        def handle_subscription(callback_query: types.CallbackQuery):
            try:
                user_id = callback_query.from_user.id
                if not check_user_in_db(user_id):
                    bot.send_message(user_id, "*❗️ Вы блокировали бота! Пропишите /start*", parse_mode="Markdown")
                subscription_type = callback_query.data.split('_')[1]
                
                price_map = {
                    "1": (subscribe_1_day, "1"),
                    "2": (subscribe_7_days, "7"),
                    "4": (subscribe_30_days, "30"),
                    "6": (subscribe_infinity_days, "3500")
                }
                amount, sub_days = price_map.get(subscription_type, (1, "1"))
                invoice = crypto.create_invoice(asset='USDT', amount=amount)
                
                pay_check = types.InlineKeyboardMarkup(row_width=2)
                pay_url = types.InlineKeyboardButton("💸 Оплатить", url=invoice['pay_url'])
                check = types.InlineKeyboardButton("🔍 Проверить", callback_data=f'check_status_{invoice["invoice_id"]}_{subscription_type}_{sub_days}')
                pay_check.add(pay_url, check)
                pay_check.add(back)
                
                bot.edit_message_text(
                    chat_id=callback_query.message.chat.id, 
                    message_id=callback_query.message.message_id,
                    text=f'*Оплата подписки*\n\n🛒 *Дней:* {sub_days}\n💳 *Цена:* {amount}$', 
                    parse_mode="Markdown", reply_markup=pay_check)
            except:
                pass

        @bot.callback_query_handler(lambda c: c.data and c.data.startswith('check_status_'))
        def check_status_callback(callback_query: types.CallbackQuery):
            try:
                parts = callback_query.data.split('_')
                if len(parts) < 4:
                    return
                invoice_id = parts[2]
                sub_days = parts[4]
                user_id = callback_query.from_user.id
                
                invoice = crypto.get_invoices(invoice_ids=invoice_id)
                if invoice['items'][0]['status'] == "paid":
                    connect = sqlite3.connect('users.db')
                    cursor = connect.cursor()
                    new_date = (datetime.now() + timedelta(days=int(sub_days))).strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("UPDATE users SET subscribe = ? WHERE user_id = ?", (new_date, user_id))
                    connect.commit()
                    connect.close()
                    bot.edit_message_text(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id,
                        text=f'✅ *Оплачено!* Подписка активирована до {new_date}', parse_mode="Markdown", reply_markup=back_markup)
                else:
                    bot.answer_callback_query(callback_query.id, "❌ Оплата не получена", show_alert=True)
            except:
                pass

        @bot.callback_query_handler(func=lambda call: True)
        def callback_inline(call):
            try:
                user_id = call.from_user.id
                if not check_user_in_db(user_id):
                    bot.send_message(user_id, "*❗️ Вы блокировали бота! Пропишите /start*", parse_mode="Markdown")
                    return
                
                connect = sqlite3.connect('users.db')
                cursor = connect.cursor()
                subscribe_str = cursor.execute("SELECT subscribe FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
                subsribe = datetime.strptime(subscribe_str, "%Y-%m-%d %H:%M:%S")
                connect.close()
                
                if call.data == 'snoser':
                    if subsribe < datetime.now():
                        bot.send_message(call.message.chat.id, '*❌ Подписка истекла!*', parse_mode="Markdown")
                        return
                    if user_id in last_used and (datetime.now() - last_used[user_id]) < timedelta(minutes=5):
                        remaining = timedelta(minutes=5) - (datetime.now() - last_used[user_id])
                        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                            text=f'❌ *Жди {remaining.seconds // 60} мин {remaining.seconds % 60} сек*', parse_mode="Markdown", reply_markup=back_markup)
                        return
                    last_used[user_id] = datetime.now()
                    msg = bot.send_message(call.message.chat.id, '🔗 *Введи ссылку на сообщение*', parse_mode="Markdown")
                    bot.register_next_step_handler(msg, get_report_link)
                    
                elif call.data == 'scam_channel':
                    if subsribe < datetime.now():
                        bot.send_message(call.message.chat.id, '*❌ Подписка истекла!*', parse_mode="Markdown")
                        return
                    msg = bot.send_message(call.message.chat.id, '🔗 *Введи ссылку на канал*\nПример: t.me/durov', parse_mode="Markdown")
                    bot.register_next_step_handler(msg, get_scam_channel)
                    
                elif call.data == 'back':
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                        text='⚡️ *ГЛАВНОЕ МЕНЮ* ⚡️', parse_mode="Markdown", reply_markup=menu)
                elif call.data == 'profile':
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                        text=f'⚡️ *ПРОФИЛЬ* ⚡️\n\n👤 *Имя:* {call.from_user.first_name}\n🆔 *ID:* `{user_id}`\n👥 *Username:* @{call.from_user.username}\n\n⏳ *Подписка до:* {subsribe}\n',
                        parse_mode="Markdown", reply_markup=back_markup)
                elif call.data == 'shop':
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                        text=f"💸 *ПОДПИСКА*\n\n1 день — {subscribe_1_day}$\n7 дней — {subscribe_7_days}$\n30 дней — {subscribe_30_days}$\nНавсегда — {subscribe_infinity_days}$\n\n*Для оплаты в рублях: {bot_admin}*",
                        parse_mode="Markdown", reply_markup=shop_markup)
                elif call.data == 'add_subsribe' and user_id in config.ADMINS:
                    msg = bot.send_message(call.message.chat.id, '➕ *Введи ID и дни через пробел*', parse_mode="Markdown")
                    bot.register_next_step_handler(msg, add_subsribe_cmd)
                elif call.data == 'clear_subscribe' and user_id in config.ADMINS:
                    msg = bot.send_message(call.message.chat.id, '❌ *Введи ID*', parse_mode="Markdown")
                    bot.register_next_step_handler(msg, clear_subscribe_cmd)
                elif call.data == 'send_all' and user_id in config.ADMINS:
                    msg = bot.send_message(call.message.chat.id, '📢 *Введи текст рассылки*', parse_mode="Markdown")
                    bot.register_next_step_handler(msg, send_all_cmd)
            except Exception as e:
                print(e)

        def get_report_link(message):
            user = message.from_user.id
            url = message.text.strip()
            try:
                chat_username, message_id = extract_username_and_message_id(url)
                bot.send_message(message.chat.id, '⚡️ *Отправка жалоб...*', parse_mode="Markdown")
                asyncio.run(main_reports(chat_username, message_id, user, is_channel=False))
            except:
                bot.send_message(message.chat.id, '❌ *Неверная ссылка!*', parse_mode="Markdown")

        def get_scam_channel(message):
            user = message.from_user.id
            channel = message.text.strip().replace('https://t.me/', '').replace('@', '')
            text = config.SCAM_TEXT
            bot.send_message(message.chat.id, f'⚠️ *Отправка SCAM жалобы на* @{channel}\n*Текст:* {text[:50]}...', parse_mode="Markdown")
            asyncio.run(main_reports(channel, None, user, is_channel=True, custom_text=text))

        def add_subsribe_cmd(message):
            try:
                uid, days = map(int, message.text.split())
                connect = sqlite3.connect('users.db')
                cursor = connect.cursor()
                new_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("UPDATE users SET subscribe = ? WHERE user_id = ?", (new_date, uid))
                connect.commit()
                connect.close()
                bot.send_message(message.chat.id, f'✅ *Выдано {days} дней*', parse_mode="Markdown")
                bot.send_message(uid, f'✅ *Админ выдал {days} дней подписки*', parse_mode="Markdown")
            except:
                bot.send_message(message.chat.id, '❌ *Ошибка*', parse_mode="Markdown")

        def clear_subscribe_cmd(message):
            try:
                uid = int(message.text)
                connect = sqlite3.connect('users.db')
                cursor = connect.cursor()
                cursor.execute("UPDATE users SET subscribe = '1999-01-01 20:00:00' WHERE user_id = ?", (uid,))
                connect.commit()
                connect.close()
                bot.send_message(message.chat.id, f'✅ *Подписка удалена*', parse_mode="Markdown")
                bot.send_message(uid, f'❌ *Подписка удалена администратором*', parse_mode="Markdown")
            except:
                bot.send_message(message.chat.id, '❌ *Ошибка*', parse_mode="Markdown")

        def send_all_cmd(message):
            connect = sqlite3.connect('users.db')
            cursor = connect.cursor()
            users = cursor.execute("SELECT user_id FROM users").fetchall()
            connect.close()
            ok = 0
            for user in users:
                try:
                    bot.send_message(user[0], f"📢 *РАССЫЛКА*\n\n{message.text}", parse_mode="Markdown")
                    ok += 1
                except:
                    pass
            bot.send_message(message.chat.id, f'✅ *Отправлено {ok} пользователям*', parse_mode="Markdown")

        @bot.message_handler(commands=['admin'])
        def admin_panel(message):
            if message.chat.id in config.ADMINS:
                bot.send_message(message.chat.id, "👑 *АДМИН ПАНЕЛЬ*", reply_markup=admin_markup, parse_mode="Markdown")

        bot.polling(none_stop=True)
    except Exception as e:
        print(e)
        time.sleep(3)
