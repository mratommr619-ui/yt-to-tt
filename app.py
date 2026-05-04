import os, json, threading, http.server, time, requests, urllib.parse
from datetime import datetime
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
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") # Render Environment ထဲက အလိုအလျောက်ယူမည်

ADMIN_ID = 1715890141
KPAY, AYAPAY, BEP20 = "09695616591", "09695616591", "0x56824c51be35937da7E60a6223E82cD1795984cC"

# Firebase Initialization
if not firebase_admin._apps:
    cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
    if cred_json: firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

app = Client("luxury_spliter_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- [ Render Survival Logic ] ---

def run_health_server():
    """Render Port Binding အတွက် Health Server"""
    port = int(os.getenv("PORT", 8080))
    httpd = http.server.HTTPServer(('', port), http.server.SimpleHTTPRequestHandler)
    print(f"🖥️ Health Server active on port {port}")
    httpd.serve_forever()

def self_ping():
    """Bot ကို Suspend မဖြစ်အောင် ၁၀ မိနစ်တစ်ခါ ပြန်နှိုးပေးသော logic"""
    if not RENDER_URL: return
    while True:
        try:
            time.sleep(600)
            r = requests.get(RENDER_URL)
            print(f"💓 Heartbeat: {r.status_code}")
        except: pass

# --- [ UI Texts & Buttons ] ---

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

def get_main_kb(lang):
    """စာရိုက်သည့်နေရာရှိ အဓိက Keyboard Menu"""
    return ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=WEB_URL))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['buy'])]
    ], resize_keyboard=True)

# --- [ Firestore Task Listener ] ---

def ack_listener():
    """Mini App မှ Submit လုပ်လိုက်သော Task များကို စောင့်ကြည့်ပြီး Ack ပို့ပေးသည်"""
    while True:
        try:
            # pending ဖြစ်နေသော task အသစ်များကို ရှာသည်
            pendings = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).get()
            for p in pendings:
                data = p.to_dict()
                uid, lang = int(data.get('user_id', 0)), data.get('lang', 'my')
                try:
                    app.send_message(uid, TEXTS[lang]['ack'], reply_markup=get_main_kb(lang))
                except: pass
                # Status ကို queued ပြောင်းလိုက်မှ bot.py (Worker) က အလုပ်စလုပ်မည်
                p.reference.update({'status': 'queued'})
            time.sleep(5)
        except Exception as e:
            print(f"Ack Listener Error: {e}")
            time.sleep(10)

# --- [ Bot Message Handlers ] ---

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
    db.collection('users').document(uid).set({
        'lang': lang, 'uid': uid, 'is_premium': False, 'expiry_date': 'N/A'
    }, merge=True)
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=get_main_kb(lang))

@app.on_message((filters.video | filters.document) & filters.private)
async def handle_forward(c, m):
    """ဗီဒီယို Forward လုပ်လိုက်လျှင် URL Parameter ဖြင့် ခလုတ်ထုတ်ပေးသည်"""
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    
    # Video Link ကို format ချသည် (Link မှာ ID ပါမှ Worker က ပြန်ယူနိုင်မည်)
    bot_me = await c.get_me()
    video_link = f"https://t.me/{bot_me.username}/{m.id}"
    encoded_link = urllib.parse.quote(video_link)
    
    # 🎯 Mini App URL မှာ ?link=... ဆိုပြီး တစ်ခါတည်း ထည့်ပေးလိုက်သည်
    dynamic_url = f"{WEB_URL}?link={encoded_link}"
    
    # စာသားအောက်ခြေတွင် ကပ်ပါမည့် Inline Button
    inline_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=dynamic_url))
    ]])
    
    await m.reply_text(TEXTS[lang]['forward_msg'], reply_markup=inline_kb)

@app.on_message(filters.regex(r"(👤 My Profile|👤 Profile)") & filters.private)
async def show_profile(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    status = "Premium Member ✅" if u_doc.get('is_premium') else "Free Member ❌"
    msg = f"👤 **User Profile**\n\n🆔 ID: `{uid}`\n👑 Status: **{status}**\n📅 Expiry: `{u_doc.get('expiry_date','N/A')}`"
    await m.reply_text(msg, reply_markup=get_main_kb(lang))

@app.on_message(filters.regex(r"(💎 Buy Premium|💎 Premium ဝယ်ရန်)") & filters.private)
async def show_buy(c, m):
    uid = m.from_user.id
    u_doc = db.collection('users').document(str(uid)).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    await m.reply_text(
        TEXTS[lang]['payment'].format(uid=uid, kpay=KPAY, ayapay=AYAPAY, bep20=BEP20), 
        reply_markup=get_main_kb(lang)
    )

# --- [ Execution ] ---

if __name__ == "__main__":
    # Render survival & Background tasks
    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()
    threading.Thread(target=ack_listener, daemon=True).start()
    
    print("🚀 App Bot (Render UI) is starting...")
    app.run()
