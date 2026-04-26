import os, json, re, http.server, threading
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- [Port Fix for Render] ---
def run_dummy_server():
    http.server.HTTPServer(('', int(os.environ.get("PORT", 8080))), 
    type('H', (http.server.SimpleHTTPRequestHandler,), {'do_GET': lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b"OK"))})).serve_forever()
threading.Thread(target=run_dummy_server, daemon=True).start()

# --- [Firebase Setup] ---
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))))
db = firestore.client()

app = Client("interface_bot", api_id=int(os.environ.get("API_ID")), api_hash=os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN"))

# --- [Admin & Payment Settings] ---
ADMIN_ID = 1715890141 
KPAY_NO = "09695616591"
AYAPAY_NO = "09695616591"
USDT_ADDRESS = "0x56824c51be35937da7E60a6223E82cD1795984cC"

TEXTS = {
    'my': {
        'start': "👋 **မင်္ဂလာပါ Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'main': "🎬 **ဗီဒီယို (သို့) Link ပို့ပေးပါ**\n\n🎁 **Trial:** ၂၄ နာရီ အခမဲ့\n💎 **Premium:** ၁ လ - ၃၀၀၀ ကျပ် / 1.0 USDT",
        'ask_name': "📝 **Movie Name ပေးပါ** (ကျော်ရန် /skip)",
        'ask_len': "⏱ **ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ?** (Default 5 မိနစ်)",
        'ask_wm': "📝 **Watermark စာသားပေးပါ** (ကျော်ရန် /skip)",
        'done': "⏳ **လက်ခံရရှိပါပြီ**\nအပိုင်းများ ပြန်ပို့ပေးပါမည်။",
        'expired': "⚠️ **သက်တမ်းကုန်သွားပါပြီ**\n\nKPay: `{}`\nAYA: `{}`\nUSDT: `{}`\n\nငွေလွှဲပြီး Screenshot ပို့ပေးပါ။".format(KPAY_NO, AYAPAY_NO, USDT_ADDRESS),
        'no_yt': "❌ YouTube မရပါ။"
    },
    'en': {
        'start': "👋 **Welcome to Movie Spliter Bot**",
        'main': "🎬 **Send Video or Link**\n\n🎁 **Trial:** 24h Free\n💎 **Premium:** 3000 MMK / 1.0 USDT",
        'ask_name': "📝 **Enter Movie Name** (Or /skip)",
        'ask_len': "⏱ **Minutes per part?** (Default 5)",
        'ask_wm': "📝 **Enter Watermark** (Or /skip)",
        'done': "⏳ **Received!** Processing...",
        'expired': "⚠️ **Expired!** Please pay to:\nKPay: `{}`\nUSDT: `{}`".format(KPAY_NO, AYAPAY_NO, USDT_ADDRESS),
        'no_yt': "❌ YouTube not supported."
    }
}

user_steps = {}

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"), InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")]])
    await m.reply_text(TEXTS['my']['start'], reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang = q.data.split("_")[1]
    uid = str(q.from_user.id)
    u_ref = db.collection('users').document(uid)
    if not u_ref.get().exists:
        u_ref.set({'lang': lang, 'expiry_date': (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")})
    else: u_ref.update({'lang': lang})
    await q.edit_message_text(TEXTS[lang]['main'])

@app.on_message(filters.photo & filters.private)
async def handle_ss(c, m):
    await m.forward(ADMIN_ID)
    await c.send_message(ADMIN_ID, f"💰 **Payment SS**\nUID: `{m.from_user.id}`")
    await m.reply_text("✅ Screenshot ရရှိပါသည်။ Admin စစ်ဆေးပြီး သက်တမ်းတိုးပေးပါမည်။")

@app.on_message((filters.video | filters.text) & filters.private)
async def handle_input(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict()
    if not u_doc: return
    lang = u_doc['lang']

    if datetime.now() > datetime.strptime(u_doc['expiry_date'], "%Y-%m-%d %H:%M:%S"):
        await m.reply_text(TEXTS[lang]['expired']); return

    data = {}
    if m.video: data = {'type': 'video', 'val': m.video.file_id}
    elif m.text:
        if m.text.startswith("/"): return
        links = re.findall(r'https?://[^\s]+', m.text)
        if not links or any(x in links[0] for x in ['youtube', 'youtu.be']): return
        data = {'type': 'link', 'val': links[0]}
    else: return

    user_steps[uid] = {'step': 'name', 'data': data, 'lang': lang}
    await m.reply_text(TEXTS[lang]['ask_name'])

@app.on_message(filters.text & filters.private)
async def steps_handler(c, m):
    uid = str(m.from_user.id)
    if uid not in user_steps: return
    step, lang = user_steps[uid]['step'], user_steps[uid]['lang']
    
    if step == 'name':
        user_steps[uid]['data']['name'] = "Movie" if m.text == "/skip" else m.text
        user_steps[uid]['step'] = 'len'
        await m.reply_text(TEXTS[lang]['ask_len'])
    elif step == 'len':
        user_steps[uid]['data']['len'] = 5 if m.text == "/skip" else int(m.text)
        user_steps[uid]['step'] = 'wm'
        await m.reply_text(TEXTS[lang]['ask_wm'])
    elif step == 'wm':
        wm = "" if m.text == "/skip" else m.text
        d = user_steps[uid]['data']
        db.collection('tasks').add({
            'user_id': uid, 'type': d['type'], 'value': d['val'],
            'name': d['name'], 'len': d['len'], 'wm': wm, 'lang': lang,
            'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
        })
        await m.reply_text(TEXTS[lang]['done'])
        del user_steps[uid]

app.run()
