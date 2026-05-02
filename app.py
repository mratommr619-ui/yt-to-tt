import os, json, re, http.server, threading, time, requests
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, WebAppInfo

# --- [Render Anti-Sleep] ---
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
        'do_GET': lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b"Bot Running"))
    }))
    httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()
threading.Thread(target=keep_alive, daemon=True).start()

# --- [Firebase Connection] ---
if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

app = Client("interface_bot", api_id=int(os.environ.get("API_ID")), api_hash=os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN"))

WEB_APP_URL = "https://your-project.web.app" # Firebase Hosting URL
ADMIN_ID = 1715890141 
BEP20_ADDR = "0x56824c51be35937da7E60a6223E82cD1795984cC"

TEXTS = {
    'my': {
        'intro': "👋 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'open_app': "🚀 Mini App ကိုဖွင့်ပါ",
        'profile_btn': "👤 ကျွန်ုပ်၏ ပရိုဖိုင်",
        'buy_btn': "💎 Premium ဝယ်ယူရန်",
        'profile_text': "🆔 **ID:** `{uid}`\n🌟 **အဆင့်:** {status}\n📅 **ကုန်ဆုံးရက်:** {exp}",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.2 USDT\n💳 **KPay:** `09695616591`\n🌐 **BEP20:** `{BEP20_ADDR}`\n⚠️ **Note:** ID `{uid}` ကို ထည့်ပါ။",
        'premium_success': "🎉 သင် Premium ဖြစ်သွားပါပြီ။\n📅 ကုန်ဆုံးရက်: `{exp}`"
    },
    'en': {
        'intro': "👋 **Welcome to Movie Spliter Bot**",
        'open_app': "🚀 Open Mini App",
        'profile_btn': "👤 My Profile",
        'buy_btn': "💎 Buy Premium",
        'profile_text': "🆔 **ID:** `{uid}`\n🌟 **Status:** {status}\n📅 **Expiry:** {exp}",
        'payment': f"💎 **Premium Upgrade**\n\n💰 **Price:** 3000 MMK / 1.2 USDT\n💳 **Pay:** `09695616591`\n🌐 **BEP20:** `{BEP20_ADDR}`\n⚠️ **Note:** Include ID `{uid}`.",
        'premium_success': "🎉 You are now Premium!\n📅 Expiry: `{exp}`"
    }
}

def get_user_status(uid):
    u_doc = db.collection('users').document(uid).get().to_dict()
    if not u_doc: return "Free", "N/A", "my"
    exp_str = u_doc.get('expiry_date', 'N/A')
    lang = u_doc.get('lang', 'my')
    if exp_str != "N/A" and datetime.now() > datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S"):
        db.collection('users').document(uid).update({'is_premium': False, 'expiry_date': 'N/A'})
        return "Free", "N/A", lang
    return ("Premium 🌟" if u_doc.get('is_premium') else "Free"), exp_str, lang

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"), InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")]])
    await m.reply_text("Choose Language / ဘာသာစကားရွေးပါ", reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang, uid = q.data.split("_")[1], str(q.from_user.id)
    u_ref = db.collection('users').document(uid)
    if not u_ref.get().exists:
        u_ref.set({'lang': lang, 'expiry_date': 'N/A', 'is_premium': False})
    else: u_ref.update({'lang': lang})
    kb = ReplyKeyboardMarkup([[TEXTS[lang]['open_app']], [TEXTS[lang]['profile_btn'], TEXTS[lang]['buy_btn']]], resize_keyboard=True)
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=kb)

@app.on_message(filters.regex("^(👤|👤 My Profile|👤 ကျွန်ုပ်၏ ပရိုဖိုင်)") & filters.private)
async def show_profile(c, m):
    uid = str(m.from_user.id)
    status, exp, lang = get_user_status(uid)
    await m.reply_text(TEXTS[lang]['profile_text'].format(uid=uid, status=status, exp=exp))

@app.on_message(filters.regex("^(💎|💎 Buy Premium|💎 Premium ဝယ်ယူရန်)") & filters.private)
async def show_payment(c, m):
    uid = str(m.from_user.id)
    u = db.collection('users').document(uid).get().to_dict()
    await m.reply_text(TEXTS[u.get('lang', 'my')]['payment'].format(uid=uid))

@app.on_message(filters.photo & filters.private)
async def handle_ss(c, m):
    await m.forward(ADMIN_ID)
    await c.send_message(ADMIN_ID, f"💰 **Payment SS**\nUID: `{m.from_user.id}`\nApprove: `/set_premium {m.from_user.id} 30`")
    await m.reply_text("✅ Sent to Admin.")

@app.on_message(filters.command("set_premium") & filters.user(ADMIN_ID))
async def admin_set(c, m):
    _, target_id, days = m.text.split()
    exp = (datetime.now() + timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
    db.collection('users').document(target_id).update({'is_premium': True, 'expiry_date': exp})
    u = db.collection('users').document(target_id).get().to_dict()
    await c.send_message(int(target_id), TEXTS[u.get('lang', 'my')]['premium_success'].format(exp=exp))
    await m.reply_text(f"✅ Success! {target_id} is now Premium.")

app.run()
