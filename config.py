import os

# Telegram Bot
TOKEN = os.getenv('TOKEN')
CRYPTO = os.getenv('CRYPTO')
ADMINS = [int(x.strip()) for x in os.getenv('ADMINS', '').split(',') if x.strip()]

# Telegram API (my.telegram.org)
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

# Пути (Railway volume)
DATA_DIR = '/app/data'
SESSION_FOLDER = os.path.join(DATA_DIR, 'sessions')
SESSIONS_URL = os.getenv('SESSIONS_URL')

# Цены
PRICE_1_DAY = float(os.getenv('PRICE_1_DAY', 1.5))
PRICE_7_DAYS = float(os.getenv('PRICE_7_DAYS', 5))
PRICE_30_DAYS = float(os.getenv('PRICE_30_DAYS', 8))
PRICE_INFINITY = float(os.getenv('PRICE_INFINITY', 12))

# SCAM текст
SCAM_TEXT = os.getenv('SCAM_TEXT', "In this channel the owner makes a drawing for money (whoever donates more money will win $200) and as soon as the drawing ends the owner kicks the winner and puts him on the blacklist.")

# Прокси
PROXY = os.getenv('PROXY')
USE_PROXY = bool(PROXY)

# Задержки
REPORT_DELAY_MIN = int(os.getenv('REPORT_DELAY_MIN', 3))
REPORT_DELAY_MAX = int(os.getenv('REPORT_DELAY_MAX', 8))
