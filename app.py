import os, json, re, http.server, threading
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- [Port Fix for Render] ---
def run_dummy_server():
    server_address = ('', int(os.environ.get("PORT", 8080)))
    httpd = http.server.HTTPServer(server_address, http.server.SimpleHTTPRequestHandler)
    httpd.serve_forever()
threading.Thread(target=run_dummy_server, daemon=True).start()

# --- Firebase Setup ---
cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(cert_dict)
if not firebase_admin._apps: firebase_admin.initialize_app(cred)
db = firestore.client()

# Settings
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")

app = Client("interface_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Temporary Data
user_steps = {}

TEXTS = {
    'my': {
        'desc': "🎬 ဗီဒီယိုပို့ပါ/Forward လုပ်ပါ။\n🔗 Link (Drive, Bilibili, FB, TikTok) ပို့ပါ။ (YT မရပါ)\n🎁 ၁ ခု အခမဲ့။ 💎 ၁ လစာ ၃၀၀၀ ကျပ်။",
        'ask_name': "🎬 Movie Name ပေးပါ (ကျော်ရန် /skip)",
        'ask_len': "⏱ ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ? (Default 5)",
        'ask_wm': "📝 Watermark စာသား (ကျော်ရန် /skip)",
        'wait': "⏳ လက်ခံရရှိပါပြီ။ ခေတ္တစောင့်ပေးပါ...",
        'buy': "💎 **Premium ဝယ်ယူရန်**\nKPay: `09695616591` (၃၀၀၀ ကျပ်)\n(သို့မဟုတ်) Premium သက်တမ်းကုန်ဆုံးသွားပါပြီ။",
        'no_yt': "❌ YouTube မရပါ။"
    },
    'en': {
        'desc': "🎬 Upload/Forward Video or Paste Link (Drive, Bilibili, FB, TikTok).\n🎁 1st video FREE. 💎 3000 MMK/Month.",
        'ask_name': "🎬 Enter Movie Name (Or /skip)",
        'ask_len': "⏱ Minutes per part? (Default 5)",
        'ask_wm': "📝 Watermark text (Or /skip)",
        'wait': "⏳ Processing... Please wait.",
        'buy': "💎 **Buy Premium**\nKPay: `09695616591` (3000 MMK)\nor Premium Expired.",
        'no_yt': "❌ YouTube links are not supported."
    }
}

@app.on_message(filters.command("start"))
async def start(client, message):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="setlang_my"),
        InlineKeyboardButton("🇺🇸 English", callback_data="setlang_en")
    ]])
    await message.reply_text("Choose Language / ဘာသာစကားရွေးပါ။", reply_markup=kb)

@app.on_callback_query(filters.regex("^setlang_"))
async def set_lang(client, callback_query):
    lang = callback_query.data.split("_")[1]
    uid = str(callback_query.from_user.id)
    u_ref = db.collection('users').document(uid)
    if not u_ref.get().exists:
        u_ref.set({'lang': lang, 'is_premium': False, 'used_trial': False, 'expiry_date': None})
    else: u_ref.update({'lang': lang})
    await callback_query.edit_message_text(TEXTS[lang]['desc'])

@app.on_message(filters.video | filters.text & filters.private)
async def handle_input(client, message):
    uid = str(message.from_user.id)
    u_ref = db.collection('users').document(uid)
    u_doc = u_ref.get().to_dict()
    if not u_doc: return
    lang = u_doc.get('lang', 'my')
    
    # Premium & Expiry Check
    is_pre = u_doc.get('is_premium', False)
    exp_date = u_doc.get('expiry_date')
    if is_pre and exp_date:
        now = datetime.now()
        exp_dt = datetime.strptime(exp_date, "%Y-%m-%d") if isinstance(exp_date, str) else exp_date
        if now > exp_dt:
            u_ref.update({'is_premium': False, 'used_trial': True})
            is_pre = False

    if not is_pre and u_doc.get('used_trial'):
        await message.reply_text(TEXTS[lang]['buy'])
        return

    data = {}
    if message.video:
        data['type'] = 'video'
        data['val'] = message.video.file_id
    else:
        if message.text.startswith("/"): return
        links = re.findall(r'https?://[^\s]+', message.text)
        if not links: return
        if 'youtube' in links[0] or 'youtu.be' in links[0]:
            await message.reply_text(TEXTS[lang]['no_yt'])
            return
        data['type'] = 'link'
        data['val'] = links[0]

    user_steps[uid] = {'step': 'name', 'data': data, 'lang': lang}
    await message.reply_text(TEXTS[lang]['ask_name'])

@app.on_message(filters.text & filters.private)
async def steps_handler(client, message):
    uid = str(message.from_user.id)
    if uid not in user_steps: return
    
    step = user_steps[uid]['step']
    lang = user_steps[uid]['lang']
    val = message.text
    
    if step == 'name':
        user_steps[uid]['data']['name'] = "Video" if val == "/skip" else val
        user_steps[uid]['step'] = 'len'
        await message.reply_text(TEXTS[lang]['ask_len'])
    elif step == 'len':
        user_steps[uid]['data']['len'] = 5 if val == "/skip" else int(val)
        user_steps[uid]['step'] = 'wm'
        await message.reply_text(TEXTS[lang]['ask_wm'])
    elif step == 'wm':
        wm = "" if val == "/skip" else val
        data = user_steps[uid]['data']
        db.collection('tasks').add({
            'user_id': uid, 'type': data['type'], 'value': data['val'],
            'name': data['name'], 'len': data['len'], 'wm': wm, 'lang': lang,
            'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
        })
        u_ref = db.collection('users').document(uid)
        if not u_ref.get().to_dict().get('is_premium'):
            u_ref.update({'used_trial': True})
        await message.reply_text(TEXTS[lang]['wait'])
        del user_steps[uid]

app.run()
