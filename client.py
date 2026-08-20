from telethon import TelegramClient, events, sync
import time

api_id = 'PUT HERE YOUR API_ID FROM API TELEGRAM'
api_hash = 'PUT HERE YOUR API_HASH FROM API TELEGRAM'
session_name = 'PUT HERE YOUR SESSION NAME'

client = TelegramClient(session_name, api_id, api_hash)
client.start()

for i in range(1000000000000000000):
    client.send_message('@your_bot_name', '/renew')
    time.sleep(20)
