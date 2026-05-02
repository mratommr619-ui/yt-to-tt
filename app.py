import os
import json
import threading
import http.server
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
)

# --- [ Configuration ] ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN") # Render ထဲကအတိုင်း TELEGRAM_TOKEN သုံးထားပါတယ်
WEB_APP_URL = "https://yttott-28862.web.app"
ADMIN_ID = 1715890141

# --- [ Render Port Fix ] ---
class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Running")

def run_server():
    port = int(os.getenv("PORT", 8080))
    server = http.server.HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# --- [ Firebase Connection ] ---
try:
    if not firebase_admin._apps:
        cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
    db = firestore.client()
except Exception as e:
    print(f"❌ Firebase Error: {e}")

# --- [ Bot Client ] ---
app = Client("spliter_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Payment Addresses
KPAY_AYA = "09695616591"
BEP20_ADDR = "0x56824c51be35937da7E60a6223E82cD1795984cC"

TEXTS = {
    'my': {
        'intro': "👋 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'open': "🚀 Mini App ကိုဖွင့်ပါ",
        'profile': "👤 ပရိုဖိုင်",
        'buy': "💎 Premium ဝယ်ရန်",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.2 USDT\n💳 **KPay/AYA:** `{KPAY_AYA}`\n🌐 **BEP20 (USDT):** `{BEP20_ADDR}`\n⚠️ **Note:** ငွေလွှဲပြီး Screenshot ကို ID နှင့်တကွ ပို့ပေးပါ။"
    },
    'en': {
        'intro': "👋 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Open Mini App",
        'profile': "👤 Profile",
        'buy': "💎 Buy Premium",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **1 Month:** 3000 MMK / 1.2 USDT\n💳 **KPay/AYA:** `{KPAY_AYA}`\n🌐 **BEP20 (USDT):** `{BEP20_ADDR}`\n⚠️ **Note:** Send payment screenshot with your ID."
    }
}

@app.on_message(filters.command("start") & filters.private)
async def start_handler(c, m):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"),
        InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    ]])
    await m.reply_text("Please choose language / ဘာသာစကားရွေးပါ", reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang = q.data.split("_")[1]
    uid = str(q.from_user.id)
    db.collection('users').document(uid).set({'lang': lang, 'is_premium': False, 'expiry_date': 'N/A'}, merge=True)
    
    kb = ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=WEB_APP_URL))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['buy'])]
    ], resize_keyboard=True)
    
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=kb)

@app.on_message(filters.regex("^(💎|💎 Buy Premium|💎 Premium ဝယ်ယူရန်)") & filters.private)
async def show_payment(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict()
    lang = u_doc.get('lang', 'my') if u_doc else 'my'
    await m.reply_text(TEXTS[lang]['payment'])

@app.on_message(filters.command("set_premium") & filters.user(ADMIN_ID))
async def admin_set(c, m):
    try:
        args = m.text.split()
        target_id, days = args[1], int(args[2])
        exp = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        db.collection('users').document(str(target_id)).update({'is_premium': True, 'expiry_date': exp})
        await m.reply_text(f"✅ Success! {target_id} is now Premium for {days} days.")
    except:
        await m.reply_text("Format: `/set_premium UID DAYS`")

if __name__ == "__main__":
    app.run()
