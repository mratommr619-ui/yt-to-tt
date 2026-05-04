import os, json, threading, http.server, time, requests, urllib.parse
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

# --- [ Configuration ] ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEB_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app/")

# Render က အလိုအလျောက်ပေးသော External URL ကို သုံးသည်
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") 
ADMIN_ID = 1715890141

KPAY, AYAPAY, BEP20 = "09695616591", "09695616591", "0x56824c51be35937da7E60a6223E82cD1795984cC"

if not firebase_admin._apps:
    cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
    if cred_json: firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()
app = Client("luxury_spliter_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- [ Render Survival Logic (Health Server & Self-Ping) ] ---

def run_health_server():
    """Render က Port ရှာတွေ့အောင် လုပ်ပေးသော server"""
    port = int(os.getenv("PORT", 8080))
    handler = http.server.SimpleHTTPRequestHandler
    httpd = http.server.HTTPServer(('', port), handler)
    print(f"🖥️ Internal Health Server active on port {port}")
    httpd.serve_forever()

def self_ping():
    """Render က Bot ကို အိပ်မပျော်အောင် ၁၀ မိနစ်တစ်ခါ ပြန်နှိုးသော logic"""
    if not RENDER_URL:
        print("⚠️ RENDER_EXTERNAL_URL မရှိလို့ Self-ping အလုပ်မလုပ်ပါ။")
        return
    
    print(f"📡 Self-ping started for {RENDER_URL}")
    while True:
        try:
            time.sleep(600) # ၁၀ မိနစ် (၆၀၀ စက္ကန့်)
            r = requests.get(RENDER_URL)
            print(f"💓 Heartbeat sent to {RENDER_URL}: Status {r.status_code}")
        except Exception as e:
            print(f"🚨 Ping Error: {e}")

# --- [ Text Dictionary ] ---

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
    """Mini App က Submit လုပ်လိုက်ရင် Ack ပို့ပေးမည့် logic"""
    while True:
        try:
            pendings = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).get()
            for p in pendings:
                data = p.to_dict()
                uid = int(data.get('user_id', 0))
                lang = data.get('lang', 'my')
                try:
                    app.send_message(uid, TEXTS[lang]['ack'], reply_markup=get_main_kb(lang))
                except: pass
                p.reference.update({'status': 'queued'})
            time.sleep(5)
        except:
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

@app.on_message((filters.video | filters.document) & filters.private)
async def handle_forward(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    
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

# --- [ Execution ] ---

if __name__ == "__main__":
    # Render Port Fix
    threading.Thread(target=run_health_server, daemon=True).start()
    # Survival Logic (Self-Ping)
    threading.Thread(target=self_ping, daemon=True).start()
    # Ack Sender logic
    threading.Thread(target=ack_listener, daemon=True).start()
    
    print("🚀 App Bot (Render) is starting with Survival Engine...")
    app.run()
