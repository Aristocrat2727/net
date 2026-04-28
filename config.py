import os

TOKEN = os.getenv('TOKEN')
CRYPTO = os.getenv('CRYPTO')
ADMINS = [int(x.strip()) for x in os.getenv('ADMINS', '').split(',') if x.strip()]

API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

SESSION_FOLDER = os.getenv('SESSION_FOLDER', '/app/sessions')
SESSIONS_URL = os.getenv('SESSIONS_URL')

BOT_LOGS = os.getenv('BOT_LOGS')
BOT_CHANNEL_LINK = os.getenv('BOT_CHANNEL_LINK')
BOT_ADMIN = os.getenv('BOT_ADMIN')
BOT_CHANNEL = os.getenv('BOT_CHANNEL')
BOT_INFORMATION = os.getenv('BOT_INFORMATION')

PRICE_1_DAY = float(os.getenv('PRICE_1_DAY', 1.5))
PRICE_7_DAYS = float(os.getenv('PRICE_7_DAYS', 5))
PRICE_30_DAYS = float(os.getenv('PRICE_30_DAYS', 8))
PRICE_INFINITY = float(os.getenv('PRICE_INFINITY', 12))

SCAM_TEXT = os.getenv('SCAM_TEXT', "In this channel the owner makes a drawing for money...")

PROXY = os.getenv('PROXY')
USE_PROXY = bool(PROXY)
REPORT_DELAY_MIN = int(os.getenv('REPORT_DELAY_MIN', 3))
REPORT_DELAY_MAX = int(os.getenv('REPORT_DELAY_MAX', 8))
