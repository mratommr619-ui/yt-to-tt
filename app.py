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

# --- [ Firebase Initialization ] ---
if not firebase_admin._apps:
    try:
        cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            # Firebase JSON string ကို dictionary အဖြစ်ပြောင်းလဲခြင်း
            firebase_dict = json.loads(cred_json)
            firebase_admin.initialize_app(credentials.Certificate(firebase_dict))
            print("Firebase Initialized Successfully.")
    except Exception as e:
        print(f"Firebase Init Error: {e}")

db = firestore.client()
app = Client("luxury_spliter_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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
    
    kb = ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=WEB_URL))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['buy'])]
    ], resize_keyboard=True)
    
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=kb)

@app.on_message(filters.regex(r"(👤 My Profile|👤 Profile)") & filters.private)
async def show_profile(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    is_premium = u_doc.get('is_premium', False)
    exp_str = u_doc.get('expiry_date', 'N/A')

    # Premium Expiry Check
    if is_premium and exp_str != 'N/A':
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            if exp_date < datetime.now():
                db.collection('users').document(uid).update({'is_premium': False, 'expiry_date': 'N/A'})
                is_premium, exp_str = False, 'N/A'
        except: pass

    status = "Premium Member ✅" if is_premium else "Free Member ❌"
    exp_label = "သက်တမ်းကုန်မည့်ရက်" if lang == 'my' else "Expired Date"
    days_label = "ကျန်ရှိရက်" if lang == 'my' else "Days Left"
    
    expiry_display = f"\n📅 {exp_label}: `{exp_str}`"
    if is_premium and exp_str != 'N/A':
        diff = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S") - datetime.now()
        expiry_display += f"\n⏳ {days_label}: `{max(0, diff.days)} days`"

    await m.reply_text(f"👤 **User Profile**\n\n🆔 ID: `{uid}`\n👑 Status: **{status}**{expiry_display}")

@app.on_message(filters.regex(r"(💎 Buy Premium|💎 Premium ဝယ်ရန်)") & filters.private)
async def show_buy(c, m):
    uid = m.from_user.id
    u_doc = db.collection('users').document(str(uid)).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    # Formatting fixes for payment text
    pay_text = TEXTS[lang]['payment'].format(uid=uid, kpay=KPAY, ayapay=AYAPAY, bep20=BEP20)
    await m.reply_text(pay_text)

@app.on_message(filters.command("set_premium") & filters.user(ADMIN_ID))
async def admin_set(c, m):
    try:
        args = m.text.split()
        target_id, days = args[1], int(args[2])
        exp_str = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        db.collection('users').document(str(target_id)).update({
            'is_premium': True, 
            'expiry_date': exp_str
        })
        await m.reply_text(f"✅ Success! `{target_id}` is Premium until `{exp_str}`.")
    except Exception as e:
        await m.reply_text(f"Format: `/set_premium <uid> <days>`\nError: {e}")

# --- [ Simple Web Server for Port Binding ] ---
def srv():
    port = int(os.getenv("PORT", 8080))
    server_address = ('', port)
    httpd = http.server.HTTPServer(server_address, http.server.SimpleHTTPRequestHandler)
    print(f"Health check server running on port {port}")
    httpd.serve_forever()

threading.Thread(target=srv, daemon=True).start()

print("Bot is starting...")
app.run()
