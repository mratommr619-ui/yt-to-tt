import os, json, threading, http.server
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

# --- [ Config ] ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = 1715890141

# --- [ Firebase Connection ] ---
if not firebase_admin._apps:
    try:
        cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
    except: pass
db = firestore.client()

app = Client("spliter_interface", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Payment Details
TEXTS = {
    'my': {
        'intro': "🎬 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Mini App ဖွင့်ပါ", 'profile': "👤 Profile", 'buy': "💎 Premium ဝယ်ရန်",
        'payment': "💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.0 USDT\n💳 **KPay/AYAPay:** `09695616591`\n🌐 **BEP20:** `0x56824c51be35937da7E60a6223E82cD1795984cC`",
        'success': "🎉 သင် Premium ဖြစ်သွားပါပြီ။\n📅 ကုန်ဆုံးရက်: `{exp}`"
    },
    'en': {
        'intro': "🎬 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Open Mini App", 'profile': "👤 Profile", 'buy': "💎 Buy Premium",
        'payment': "💎 **Premium Upgrade**\n\n💰 **1 Month:** 3000 MMK / 1.0 USDT\n💳 **KPay/AYAPay:** `09695616591`\n🌐 **BEP20:** `0x56824c51be35937da7E60a6223E82cD1795984cC`",
        'success': "🎉 You are now Premium!\n📅 Expiry: `{exp}`"
    }
}

@app.on_message(filters.command("start") & filters.private)
async def start_handler(c, m):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"),
        InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    ]])
    await m.reply_text("Choose Language / ဘာသာစကားရွေးပါ", reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang = q.data.split("_")[1]
    uid = str(q.from_user.id)
    db.collection('users').document(uid).set({'lang': lang, 'is_premium': False, 'expiry_date': 'N/A'}, merge=True)
    kb = ReplyKeyboardMarkup([[KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=os.getenv("WEB_APP_URL")))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['buy'])]], resize_keyboard=True)
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
        await m.reply_text(f"✅ Success! {target_id} is Premium.")
    except: await m.reply_text("Format: `/set_premium UID DAYS`")

# Render Port Binding
def run_server():
    http.server.HTTPServer(('0.0.0.0', int(os.getenv("PORT", 8080))), http.server.SimpleHTTPRequestHandler).serve_forever()
threading.Thread(target=run_server, daemon=True).start()

app.run()
