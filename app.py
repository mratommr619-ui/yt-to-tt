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
        'profile': "👤 My Profile",
        'buy': "💎 Premium ဝယ်ရန်",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.0 USDT\n💳 **KPay:** `{KPAY}`\n💳 **AYAPay:** `{AYAPAY}`\n🌐 **BEP20:** `{BEP20}`\n⚠️ **Note:** ID `{{uid}}` ကို Screenshot နှင့်အတူ ပို့ပေးပါ။",
        'success': "🎉 သင် Premium ဖြစ်သွားပါပြီ။"
    },
    'en': {
        'intro': "🎬 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Open Mini App",
        'profile': "👤 My Profile",
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
    
    kb = ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=WEB_URL))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['buy'])]
    ], resize_keyboard=True)
    
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=kb)

# --- [ Profile logic with Date calculation ] ---
@app.on_message(filters.regex(r"👤 My Profile") & filters.private)
async def show_profile(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    
    is_premium = u_doc.get('is_premium', False)
    status_icon = "Premium ✅" if is_premium else "Free Member ❌"
    
    expiry_info = ""
    if is_premium:
        exp_str = u_doc.get('expiry_date') # Format: YYYY-MM-DD HH:MM:SS
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            
            if exp_date > now:
                diff = exp_date - now
                days_left = diff.days
                # မြန်မာ/အင်္ဂလိပ် အလိုက် ပြမယ်
                if lang == 'my':
                    expiry_info = f"\n📅 ကုန်ဆုံးရက်: `{exp_str}`\n⏳ ကျန်ရှိရက်: `{days_left} ရက်`"
                else:
                    expiry_info = f"\n📅 Expiry Date: `{exp_str}`\n⏳ Days Left: `{days_left} days`"
            else:
                # Expired ဖြစ်သွားရင် premium ပြန်ဖြုတ်မယ်
                db.collection('users').document(uid).update({'is_premium': False})
                status_icon = "Free Member (Expired) ❌"
        except:
            expiry_info = f"\n📅 Expiry: `{exp_str}`"

    profile_text = f"👤 **Your Profile**\n\n🆔 ID: `{uid}`\n👑 Status: {status_icon}{expiry_info}"
    await m.reply_text(profile_text)

# Premium Buy Button Handle
@app.on_message(filters.regex(r"(💎 Buy Premium|💎 Premium ဝယ်ရန်)") & filters.private)
async def show_buy(c, m):
    uid = m.from_user.id
    u_doc = db.collection('users').document(str(uid)).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    await m.reply_text(TEXTS[lang]['payment'].format(uid=uid))

# Admin command: /set_premium <uid> <days>
@app.on_message(filters.command("set_premium") & filters.user(ADMIN_ID))
async def admin_set(c, m):
    try:
        args = m.text.split()
        target_id, days = args[1], int(args[2])
        # လက်ရှိအချိန်ကနေ သတ်မှတ်ရက်ပေါင်းထည့်မယ်
        exp_dt = datetime.now() + timedelta(days=days)
        exp_str = exp_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        db.collection('users').document(str(target_id)).update({
            'is_premium': True, 
            'expiry_date': exp_str
        })
        await m.reply_text(f"✅ Success!\nUser: `{target_id}`\nDuration: `{days}` days\nExpiry: `{exp_str}`")
    except Exception as e:
        await m.reply_text("Format: `/set_premium <uid> <days>`")

def srv():
    http.server.HTTPServer(('0.0.0.0', int(os.getenv("PORT", 8080))), http.server.SimpleHTTPRequestHandler).serve_forever()
threading.Thread(target=srv, daemon=True).start()

app.run()
