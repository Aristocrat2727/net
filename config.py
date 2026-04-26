import os

TOKEN = os.getenv('TOKEN')
CRYPTO = os.getenv('CRYPTO')
ADMINS = [int(x.strip()) for x in os.getenv('ADMINS', '').split(',') if x.strip()]

API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

SESSION_FOLDER = os.getenv('SESSION_FOLDER', '/app/sessions')
