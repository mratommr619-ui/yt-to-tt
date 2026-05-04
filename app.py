import os, json, threading, http.server, time, requests, urllib.parse
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
SERVER_URL = os.getenv("SERVER_URL", "") 
ADMIN_ID = 1715890141

KPAY, AYAPAY, BEP20 = "09695616591", "09695616591", "0x56824c51be35937da7E60a6223E82cD1795984cC"

if not firebase_admin._apps:
    cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
    if cred_json: firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()
app = Client("luxury_spliter_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- [ Original Text Logic ] ---
TEXTS = {
    'my': {
        'intro': "🎬 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'open': "🚀 Mini App ဖွင့်ရန်",
        'profile': "👤 My Profile",
        'buy': "💎 Premium ဝယ်ရန်",
        'payment': "💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.0 USDT\n💳 **KPay:** `{kpay}`\n💳 **AYAPay:** `{ayapay}`\n🌐 **BEP20:** `{bep20}`\n⚠️ **Note:** ID `{uid}` ကို Screenshot နှင့်အတူ ပို့ပေးပါ။",
        'forward_msg': "✅ ဗီဒီယိုကို မှတ်မိပါသည်။ Mini App တွင် အသေးစိတ်ဖြည့်ရန် အောက်ပါခလုတ်ကို နှိပ်ပါ။",
        'ack': "ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။ အပိုင်းများခွဲပြီးပါက ပြန်လည်ပို့ဆောင်ပေးပါမည်။"
    },
    'en': {
        'intro': "🎬 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Open Mini App",
        'profile': "👤 My Profile",
        'buy': "💎 Buy Premium",
        'payment': "💎 **Premium Upgrade**\n\n💰 **1 Month:** 3000 MMK / 1.0 USDT\n💳 **KPay:** `{kpay}`\n💳 **AYAPay:** `{ayapay}`\n🌐 **BEP20:** `{bep20}`\n⚠️ **Note:** Send ID `{uid}` with screenshot.",
        'forward_msg': "✅ Video recognized! Click the button below to open Mini App.",
        'ack': "Video received! Please wait. Your split videos will be sent soon."
    }
}

def get_main_kb(lang, web_url=WEB_URL):
    return ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=web_url))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['buy'])]
    ], resize_keyboard=True)

# --- [ Background Task: Ack Sender ] ---
def ack_listener():
    """Mini App ကနေ Submit လုပ်လိုက်လို့ Firebase ထဲ Task ရောက်လာရင် Ack message ပို့ပေးမည့် logic"""
    while True:
        try:
            pendings = db.collection('tasks').where('status', '==', 'pending').get()
            for p in pendings:
                data = p.to_dict()
                uid = int(data.get('user_id', 0))
                lang = data.get('lang', 'my')
                # Ack ပို့သည်
                app.send_message(uid, TEXTS[lang]['ack'], reply_markup=get_main_kb(lang))
                # Status ကို queued ပြောင်းလိုက်မှ bot.py က အလုပ်စလုပ်မည်
                p.reference.update({'status': 'queued'})
            time.sleep(5)
        except Exception as e:
            print(f"Ack Error: {e}")
            time.sleep(10)

# --- [ Bot Handlers ] ---
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
    db.collection('users').document(uid).set({'lang': lang, 'uid': uid, 'is_premium': False, 'expiry_date': 'N/A'}, merge=True)
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=get_main_kb(lang))

# New: Video Forward Handler
@app.on_message((filters.video | filters.document) & filters.private)
async def handle_forward(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    
    # Message Link ယူခြင်း
    video_link = f"https://t.me/me/{m.id}"
    encoded_link = urllib.parse.quote(video_link)
    dynamic_url = f"{WEB_URL}?link={encoded_link}"
    
    await m.reply_text(TEXTS[lang]['forward_msg'], reply_markup=get_main_kb(lang, dynamic_url))

@app.on_message(filters.regex(r"(👤 My Profile|👤 Profile)") & filters.private)
async def show_profile(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    status = "Premium Member ✅" if u_doc.get('is_premium', False) else "Free Member ❌"
    await m.reply_text(f"👤 **User Profile**\n\n🆔 ID: `{uid}`\n👑 Status: **{status}**\n📅 Expiry: `{u_doc.get('expiry_date', 'N/A')}`", reply_markup=get_main_kb(lang))

@app.on_message(filters.regex(r"(💎 Buy Premium|💎 Premium ဝယ်ရန်)") & filters.private)
async def show_buy(c, m):
    uid = m.from_user.id
    u_doc = db.collection('users').document(str(uid)).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    await m.reply_text(TEXTS[lang]['payment'].format(uid=uid, kpay=KPAY, ayapay=AYAPAY, bep20=BEP20), reply_markup=get_main_kb(lang))

if __name__ == "__main__":
    threading.Thread(target=ack_listener, daemon=True).start()
    app.run()
