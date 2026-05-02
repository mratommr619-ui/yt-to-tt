import os, json, http.server, threading, time, requests
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

# --- [အချက်အလက်များ - Direct Integration] ---
API_ID = 36969505
API_HASH = "f129bfcfe08725b285d2a1938fc18380"
BOT_TOKEN = "8557322288:AAFAmQeE2T3IXTezumLomW6m-0f37qyR3I4"
WEB_APP_URL = "https://yttott-28862.web.app"
ADMIN_ID = 1715890141 

# --- [Render Anti-Sleep Logic] ---
def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    while True:
        try:
            if url: requests.get(url, timeout=10)
        except: pass
        time.sleep(600)

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    httpd = http.server.HTTPServer(('', port), type('H', (http.server.SimpleHTTPRequestHandler,), {
        'do_GET': lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b"Bot is Active"))
    }))
    httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()
threading.Thread(target=keep_alive, daemon=True).start()

# --- [Firebase Connection] ---
if not firebase_admin._apps:
    try:
        cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
    except Exception as e: print(f"Firebase Error: {e}")

db = firestore.client()
app = Client("interface_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- [Language Texts] ---
TEXTS = {
    'my': {
        'intro': "👋 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'open_app': "🚀 Mini App ကိုဖွင့်ပါ",
        'profile_btn': "👤 ကျွန်ုပ်၏ ပရိုဖိုင်",
        'buy_btn': "💎 Premium ဝယ်ယူရန်",
        'profile_text': "🆔 **ID:** `{uid}`\n🌟 **အဆင့်:** {status}\n📅 **ကုန်ဆုံးရက်:** {exp}",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.2 USDT\n💳 **KPay:** `09695616591`\n⚠️ **Note:** ID `{{uid}}` ကို Screenshot နှင့်အတူ ပို့ပေးပါ။",
        'premium_success': "🎉 သင် Premium ဖြစ်သွားပါပြီ။\n📅 ကုန်ဆုံးရက်: `{exp}`"
    },
    'en': {
        'intro': "👋 **Welcome to Movie Spliter Bot**",
        'open_app': "🚀 Open Mini App",
        'profile_btn': "👤 My Profile",
        'buy_btn': "💎 Buy Premium",
        'profile_text': "🆔 **ID:** `{uid}`\n🌟 **Status:** {status}\n📅 **Expiry:** {exp}",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **1 Month:** 3000 MMK / 1.2 USDT\n💳 **KPay:** `09695616591`\n⚠️ **Note:** Send ID `{{uid}}` with screenshot.",
        'premium_success': "🎉 You are now Premium!\n📅 Expiry: `{exp}`"
    }
}

def get_user_status(uid):
    u_ref = db.collection('users').document(str(uid)).get()
    if not u_ref.exists: return "Free", "N/A", "my"
    u_doc = u_ref.to_dict()
    exp_str = u_doc.get('expiry_date', 'N/A')
    lang = u_doc.get('lang', 'my')
    if exp_str != "N/A" and datetime.now() > datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S"):
        db.collection('users').document(str(uid)).update({'is_premium': False, 'expiry_date': 'N/A'})
        return "Free", "N/A", lang
    return ("Premium 🌟" if u_doc.get('is_premium') else "Free"), exp_str, lang

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
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
    
    kb = ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['open_app'], web_app=WebAppInfo(url=WEB_APP_URL))],
        [KeyboardButton(TEXTS[lang]['profile_btn']), KeyboardButton(TEXTS[lang]['buy_btn'])]
    ], resize_keyboard=True)
    
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=kb)

@app.on_message(filters.regex("^(👤|👤 My Profile|👤 ကျွန်ုပ်၏ ပရိုဖိုင်)") & filters.private)
async def show_profile(c, m):
    uid = m.from_user.id
    status, exp, lang = get_user_status(uid)
    await m.reply_text(TEXTS[lang]['profile_text'].format(uid=uid, status=status, exp=exp))

@app.on_message(filters.regex("^(💎|💎 Buy Premium|💎 Premium ဝယ်ယူရန်)") & filters.private)
async def show_payment(c, m):
    uid = m.from_user.id
    _, _, lang = get_user_status(uid)
    await m.reply_text(TEXTS[lang]['payment'].format(uid=uid))

@app.on_message(filters.photo & filters.private)
async def handle_ss(c, m):
    await m.forward(ADMIN_ID)
    await c.send_message(ADMIN_ID, f"💰 **Payment Received**\nUID: `{m.from_user.id}`\nApprove: `/set_premium {m.from_user.id} 30`")
    await m.reply_text("✅ Screenshot sent to Admin. Please wait.")

@app.on_message(filters.command("set_premium") & filters.user(ADMIN_ID))
async def admin_set(c, m):
    try:
        args = m.text.split()
        target_id, days = args[1], int(args[2])
        exp = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        db.collection('users').document(str(target_id)).update({'is_premium': True, 'expiry_date': exp})
        _, _, lang = get_user_status(target_id)
        await c.send_message(int(target_id), TEXTS[lang]['premium_success'].format(exp=exp))
        await m.reply_text(f"✅ Success! {target_id} is Premium.")
    except Exception as e: await m.reply_text(f"❌ Error: {e}")

app.run()
