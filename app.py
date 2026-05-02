import os, json, threading, http.server
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
import firebase_admin
from firebase_admin import credentials, firestore

# --- [ Configuration ] ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEB_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app/")
ADMIN_ID = 1715890141

# Payment Info
KPAY = "09695616591"
AYAPAY = "09695616591"
BEP20 = "0x56824c51be35937da7E60a6223E82cD1795984cC"

# --- [ Firebase ] ---
if not firebase_admin._apps:
    try:
        cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
    except: pass
db = firestore.client()

app = Client("luxury_spliter_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

TEXTS = {
    'my': {
        'intro': "🎬 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'open': "🚀 Mini App ဖွင့်ရန်",
        'profile': "👤 Profile",
        'buy': "💎 Premium ဝယ်ယူရန်",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.0 USDT\n💳 **KPay:** `{KPAY}`\n💳 **AYAPay:** `{AYAPAY}`\n🌐 **BEP20:** `{BEP20}`\n⚠️ **Note:** ID `{{uid}}` ကို Screenshot နှင့်အတူ ပို့ပေးပါ။",
        'success': "🎉 သင် Premium ဖြစ်သွားပါပြီ။"
    },
    'en': {
        'intro': "🎬 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Open Mini App",
        'profile': "👤 Profile",
        'buy': "💎 Buy Premium",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **1 Month:** 3000 MMK / 1.0 USDT\n💳 **KPay:** `{KPAY}`\n💳 **AYAPay:** `{AYAPAY}`\n🌐 **BEP20:** `{BEP20}`\n⚠️ **Note:** Send ID `{{uid}}` with screenshot.",
        'success': "🎉 You are now Premium!"
    }
}

@app.on_message(filters.command("start") & filters.private)
async def start(c, m):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"),
        InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    ]])
    await m.reply_text("Choose Language / ဘာသာစကားရွေးချယ်ပါ -", reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang = q.data.split("_")[1]
    uid = str(q.from_user.id)
    db.collection('users').document(uid).set({'lang': lang, 'uid': uid}, merge=True)
    kb = ReplyKeyboardMarkup([[KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=WEB_URL))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['buy'])]], resize_keyboard=True)
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=kb)

@app.on_message(filters.regex("^(💎|💎 Buy Premium|💎 Premium ဝယ်ယူရန်)") & filters.private)
async def show_payment(c, m):
    uid = m.from_user.id
    u = db.collection('users').document(str(uid)).get().to_dict()
    lang = u.get('lang', 'my') if u else 'my'
    await m.reply_text(TEXTS[lang]['payment'].format(uid=uid))

@app.on_message(filters.command("set_premium") & filters.user(ADMIN_ID))
async def admin_set(c, m):
    try:
        args = m.text.split()
        target_id, days = args[1], int(args[2])
        exp = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        db.collection('users').document(str(target_id)).update({'is_premium': True, 'expiry_date': exp})
        await m.reply_text(f"✅ Success! {target_id} is Premium.")
    except: pass

def srv():
    http.server.HTTPServer(('0.0.0.0', int(os.getenv("PORT", 8080))), http.server.SimpleHTTPRequestHandler).serve_forever()
threading.Thread(target=srv, daemon=True).start()

app.run()
