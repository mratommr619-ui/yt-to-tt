import os, json, threading, http.server
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

# --- [ Environment Variables ] ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1715890141"))

# --- [ Firebase Connection ] ---
if not firebase_admin._apps:
    try:
        cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
    except Exception as e:
        print(f"Firebase Init Error: {e}")

db = firestore.client()
app = Client("interface_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Payment Information
KPAY_NUM = "09695616591"
AYAPAY_NUM = "09695616591"
BEP20_ADDR = "0x56824c51be35937da7E60a6223E82cD1795984cC"

TEXTS = {
    'my': {
        'intro': "👋 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'open': "🚀 Mini App ကိုဖွင့်ပါ",
        'profile': "👤 ပရိုဖိုင်",
        'buy': "💎 Premium ဝယ်ရန်",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.0 USDT\n💳 **KPay:** `{KPAY_NUM}`\n💳 **AYAPay:** `{AYAPAY_NUM}`\n🌐 **BEP20:** `{BEP20_ADDR}`\n⚠️ **Note:** ID `{{uid}}` ကို Screenshot နှင့်အတူ ပို့ပေးပါ။",
        'premium_success': "🎉 သင် Premium ဖြစ်သွားပါပြီ။\n📅 ကုန်ဆုံးရက်: `{exp}`"
    },
    'en': {
        'intro': "👋 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Open Mini App",
        'profile': "👤 Profile",
        'buy': "💎 Buy Premium",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **1 Month:** 3000 MMK / 1.0 USDT\n💳 **KPay:** `{KPAY_NUM}`\n💳 **AYAPay:** `{AYAPAY_NUM}`\n🌐 **BEP20:** `{BEP20_ADDR}`\n⚠️ **Note:** Send ID `{{uid}}` with screenshot.",
        'premium_success': "🎉 You are now Premium!\n📅 Expiry: `{exp}`"
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
    uid = m.from_user.id
    u_ref = db.collection('users').document(str(uid)).get()
    lang = u_ref.to_dict().get('lang', 'my') if u_ref.exists else 'my'
    await m.reply_text(TEXTS[lang]['payment'].format(uid=uid))

@app.on_message(filters.photo & filters.private)
async def handle_ss(c, m):
    await m.forward(ADMIN_ID)
    await c.send_message(ADMIN_ID, f"💰 **Payment SS Received**\nUID: `{m.from_user.id}`\nApprove via: `/set_premium {m.from_user.id} 30`")
    await m.reply_text("✅ Screenshot sent to Admin. Please wait.")

@app.on_message(filters.command("set_premium") & filters.user(ADMIN_ID))
async def admin_set(c, m):
    try:
        args = m.text.split()
        target_id, days = args[1], int(args[2])
        exp = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        db.collection('users').document(str(target_id)).update({'is_premium': True, 'expiry_date': exp})
        u_doc = db.collection('users').document(str(target_id)).get().to_dict()
        lang = u_doc.get('lang', 'my')
        await c.send_message(int(target_id), TEXTS[lang]['premium_success'].format(exp=exp))
        await m.reply_text(f"✅ Success! {target_id} is Premium.")
    except: pass

def start_server():
    port = int(os.getenv("PORT", 8080))
    http.server.HTTPServer(('', port), http.server.SimpleHTTPRequestHandler).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_server, daemon=True).start()
    app.run()
