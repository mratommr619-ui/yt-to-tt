import os
import json
import threading
import http.server
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    WebAppInfo
)

# --- [ Environment Setup ] ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1715890141"))

# --- [ Firebase Connection ] ---
try:
    if not firebase_admin._apps:
        # FIREBASE_SERVICE_ACCOUNT variable ထဲမှာ JSON တစ်ခုလုံး ရှိရပါမယ်
        cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            cred_dict = json.loads(cred_json)
            firebase_admin.initialize_app(credentials.Certificate(cred_dict))
    db = firestore.client()
    print("✅ Firebase Connected Successfully")
except Exception as e:
    print(f"❌ Firebase Error: {e}")

# --- [ Bot Setup ] ---
app = Client("spliter_interface", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# စာသားများ (မြန်မာ/အင်္ဂလိပ်)
TEXTS = {
    'my': {
        'intro': "👋 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'open': "🚀 Mini App ကိုဖွင့်ပါ",
        'profile': "👤 ပရိုဖိုင်",
        'buy': "💎 Premium ဝယ်ရန်",
        'status': "🆔 **ID:** `{uid}`\n🌟 **Status:** {status}\n📅 **Expiry:** {exp}"
    },
    'en': {
        'intro': "👋 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Open Mini App",
        'profile': "👤 My Profile",
        'buy': "💎 Buy Premium",
        'status': "🆔 **ID:** `{uid}`\n🌟 **Status:** {status}\n📅 **Expiry:** {exp}"
    }
}

# --- [ Handlers ] ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(c, m):
    # Language ရွေးခိုင်းမယ်
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"),
        InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    ]])
    await m.reply_text("Please choose language / ဘာသာစကားရွေးပါ", reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang = q.data.split("_")[1]
    uid = str(q.from_user.id)
    
    # Firebase မှာ သိမ်းမယ်
    db.collection('users').document(uid).set({
        'lang': lang,
        'is_premium': False,
        'expiry_date': 'N/A'
    }, merge=True)
    
    # Menu ပြမယ်
    kb = ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=WEB_APP_URL))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['buy'])]
    ], resize_keyboard=True)
    
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=kb)

# --- [ Render Support ] ---
def run_server():
    port = int(os.getenv("PORT", 8080))
    server = http.server.HTTPServer(('', port), http.server.SimpleHTTPRequestHandler)
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    print("🤖 Bot is starting...")
    app.run()
