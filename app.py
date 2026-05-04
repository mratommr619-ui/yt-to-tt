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
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") 

ADMIN_ID = 1715890141
KPAY, AYAPAY, BEP20 = "09695616591", "09695616591", "0x56824c51be35937da7E60a6223E82cD1795984cC"

if not firebase_admin._apps:
    cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
    if cred_json: firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()
app = Client("luxury_spliter_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- [ Survival Logic ] ---
def run_health_server():
    port = int(os.getenv("PORT", 8080))
    httpd = http.server.HTTPServer(('', port), http.server.SimpleHTTPRequestHandler)
    httpd.serve_forever()

def self_ping():
    if not RENDER_URL: return
    while True:
        try:
            time.sleep(600)
            requests.get(RENDER_URL)
        except: pass

# --- [ UI & Logic ] ---
TEXTS = {
    'my': {
        'intro': "🎬 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'open': "🚀 Mini App ဖွင့်ရန်",
        'profile': "👤 My Profile",
        'buy': "💎 Premium ဝယ်ရန်",
        'payment': "💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.0 USDT\n💳 **KPay:** `{kpay}`\n💳 **AYAPay:** `{ayapay}`\n🌐 **BEP20:** `{bep20}`\n⚠️ **Note:** ID `{uid}` ကို Screenshot နှင့်အတူ ပို့ပေးပါ။",
        'forward_msg': "✅ **ဗီဒီယိုကို မှတ်မိပါသည်။**\n\n🔗 လင့်ခ်ကို ကူးယူရန် နှိပ်ပါ -\n`{v_link}`\n\nအပေါ်ကလင့်ခ်ကို ကော်ပီကူးပြီး Mini App ထဲက လင့်ခ်နေရာမှာ ထည့်ပေးပါ။",
        'ack': "ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။"
    },
    'en': {
        'intro': "🎬 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Open Mini App",
        'profile': "👤 My Profile",
        'buy': "💎 Buy Premium",
        'payment': "💎 **Premium Upgrade**\n\n💰 **1 Month:** 3000 MMK / 1.0 USDT\n💳 **KPay:** `{kpay}`\n💳 **AYAPay:** `{ayapay}`\n🌐 **BEP20:** `{bep20}`\n⚠️ **Note:** Send ID `{uid}` with screenshot.",
        'forward_msg': "✅ **Video recognized!**\n\n🔗 Tap to copy link -\n`{v_link}`\n\nCopy the link above and paste it in the Mini App.",
        'ack': "Video received! Please wait."
    }
}

def get_main_kb(lang, web_url=WEB_URL):
    return ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=web_url))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['buy'])]
    ], resize_keyboard=True)

def ack_listener():
    while True:
        try:
            pendings = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).get()
            for p in pendings:
                data = p.to_dict()
                uid, lang = int(data.get('user_id', 0)), data.get('lang', 'my')
                app.send_message(uid, TEXTS[lang]['ack'], reply_markup=get_main_kb(lang))
                p.reference.update({'status': 'queued'})
            time.sleep(5)
        except: time.sleep(10)

# --- [ Handlers ] ---

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

@app.on_message((filters.video | filters.document) & filters.private & filters.incoming)
async def handle_forward(c, m):
    if m.outgoing: return
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    
    bot_info = await c.get_me()
    video_link = f"https://t.me/{bot_info.username}/{m.id}"
    encoded_link = urllib.parse.quote(video_link)
    
    caption = TEXTS[lang]['forward_msg'].format(v_link=video_link)
    inline_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=f"{WEB_URL}?link={encoded_link}"))
    ]])
    
    await m.reply_text(caption, reply_markup=inline_kb)

@app.on_message(filters.regex(r"(👤 My Profile|👤 Profile)") & filters.private)
async def show_profile(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    status = "Premium Member ✅" if u_doc.get('is_premium') else "Free Member ❌"
    await m.reply_text(f"👤 **Profile**\n🆔: `{uid}`\n👑: {status}\n📅: {u_doc.get('expiry_date','N/A')}", reply_markup=get_main_kb(lang))

@app.on_message(filters.regex(r"(💎 Buy Premium|💎 Premium ဝယ်ရန်)") & filters.private)
async def show_buy(c, m):
    uid = m.from_user.id
    u_doc = db.collection('users').document(str(uid)).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    await m.reply_text(TEXTS[lang]['payment'].format(uid=uid, kpay=KPAY, ayapay=AYAPAY, bep20=BEP20), reply_markup=get_main_kb(lang))

if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()
    threading.Thread(target=ack_listener, daemon=True).start()
    app.run()
