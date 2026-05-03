import os, json, threading, http.server, time, requests
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
# မိတ်ဆွေရဲ့ Bot Web Service URL (ဥပမာ- Render/Heroku ကပေးတဲ့ link)
SERVER_URL = os.getenv("SERVER_URL", "") 
ADMIN_ID = 1715890141

KPAY, AYAPAY, BEP20 = "09695616591", "09695616591", "0x56824c51be35937da7E60a6223E82cD1795984cC"

if not firebase_admin._apps:
    cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
    if cred_json: firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()
app = Client("luxury_spliter_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- [ Keep-Alive & Self-Ping Logic ] ---
def self_ping():
    """၁၀ မိနစ်တစ်ခါ Server ကို လှမ်းခေါက်ပြီး နိုးနေအောင်လုပ်ပေးသော logic"""
    if not SERVER_URL:
        print("⚠️ SERVER_URL environment variable မရှိလို့ Self-ping အလုပ်မလုပ်ပါ။")
        return
    
    print(f"📡 Self-ping started for {SERVER_URL}")
    while True:
        try:
            # ၁၀ မိနစ် (၆၀၀ စက္ကန့်) တစ်ခါ ping ပါမယ်
            time.sleep(600) 
            r = requests.get(SERVER_URL)
            print(f"💓 Heartbeat sent: Status {r.status_code}")
        except Exception as e:
            print(f"🚨 Ping Error: {e}")

def run_health_server():
    port = int(os.getenv("PORT", 8080))
    server = http.server.HTTPServer(('', port), http.server.SimpleHTTPRequestHandler)
    print(f"🖥️ Internal Health Server active on port {port}")
    server.serve_forever()

# --- [ Original Bot Logic - No Changes ] ---
TEXTS = {
    'my': {
        'intro': "🎬 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'open': "🚀 Mini App ဖွင့်ရန်",
        'profile': "👤 My Profile",
        'buy': "💎 Premium ဝယ်ရန်",
        'payment': "💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.0 USDT\n💳 **KPay:** `{kpay}`\n💳 **AYAPay:** `{ayapay}`\n🌐 **BEP20:** `{bep20}`\n⚠️ **Note:** ID `{uid}` ကို Screenshot နှင့်အတူ ပို့ပေးပါ။",
    },
    'en': {
        'intro': "🎬 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Open Mini App",
        'profile': "👤 My Profile",
        'buy': "💎 Buy Premium",
        'payment': "💎 **Premium Upgrade**\n\n💰 **1 Month:** 3000 MMK / 1.0 USDT\n💳 **KPay:** `{kpay}`\n💳 **AYAPay:** `{ayapay}`\n🌐 **BEP20:** `{bep20}`\n⚠️ **Note:** Send ID `{uid}` with screenshot.",
    }
}

def get_main_kb(lang):
    return ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=WEB_URL))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['buy'])]
    ], resize_keyboard=True)

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

@app.on_message(filters.regex(r"(👤 My Profile|👤 Profile)") & filters.private)
async def show_profile(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    is_premium = u_doc.get('is_premium', False)
    exp_str = u_doc.get('expiry_date', 'N/A')
    
    if is_premium and exp_str != 'N/A':
        try:
            if datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S") < datetime.now():
                db.collection('users').document(uid).update({'is_premium': False, 'expiry_date': 'N/A'})
                is_premium, exp_str = False, 'N/A'
        except: pass

    status = "Premium Member ✅" if is_premium else "Free Member ❌"
    await m.reply_text(f"👤 **User Profile**\n\n🆔 ID: `{uid}`\n👑 Status: **{status}**\n📅 Expiry: `{exp_str}`", reply_markup=get_main_kb(lang))

@app.on_message(filters.regex(r"(💎 Buy Premium|💎 Premium ဝယ်ရန်)") & filters.private)
async def show_buy(c, m):
    uid = m.from_user.id
    u_doc = db.collection('users').document(str(uid)).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    await m.reply_text(TEXTS[lang]['payment'].format(uid=uid, kpay=KPAY, ayapay=AYAPAY, bep20=BEP20), reply_markup=get_main_kb(lang))

# --- [ Execution ] ---
if __name__ == "__main__":
    # Internal Server
    threading.Thread(target=run_health_server, daemon=True).start()
    # Self-Ping Background Task
    threading.Thread(target=self_ping, daemon=True).start()
    
    print("🚀 App Bot is starting with Self-Ping Engine...")
    app.run()
