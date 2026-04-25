import os, json, re, http.server, threading
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- [Render Port Error Fix] ---
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('', port)
    httpd = http.server.HTTPServer(server_address, http.server.SimpleHTTPRequestHandler)
    print(f"Dummy server running on port {port}")
    httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# --- [Firebase Setup] ---
if not firebase_admin._apps:
    cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(cert_dict)
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- [Bot Setup] ---
app = Client(
    "interface_bot",
    api_id=int(os.environ.get("API_ID")),
    api_hash=os.environ.get("API_HASH"),
    bot_token=os.environ.get("TELEGRAM_TOKEN")
)

user_steps = {}

TEXTS = {
    'my': {
        'desc': "🎬 ဗီဒီယိုပို့ပါ/Forward လုပ်ပါ။\n🔗 Link (Drive, Bilibili, FB, TikTok) ပို့ပါ။ (YT မရပါ)\n🎁 ၁ ခု အခမဲ့။ 💎 ၁ လစာ ၃၀၀၀ ကျပ်။",
        'ask_name': "🎬 Movie Name ပေးပါ (ကျော်ရန် /skip)",
        'ask_len': "⏱ ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ? (Default 5)",
        'ask_wm': "📝 Watermark စာသား (ကျော်ရန် /skip)",
        'wait': "⏳ အချက်အလက်များ လက်ခံရရှိပါပြီ။ ခေတ္တစောင့်ပေးပါ...",
        'buy': "💎 **Premium ဝယ်ယူရန်**\nKPay: `09695616591` (၃၀၀၀ ကျပ်)\nသက်တမ်းကုန်သွားပါက ထပ်မံဝယ်ယူရပါမည်။",
        'no_yt': "❌ YouTube မရပါ။"
    },
    'en': {
        'desc': "🎬 Upload/Forward Video or Paste Link.\n🎁 1st video FREE. 💎 3000 MMK/Month.",
        'ask_name': "🎬 Enter Movie Name (Or /skip)",
        'ask_len': "⏱ Minutes per part? (Default 5)",
        'ask_wm': "📝 Watermark text (Or /skip)",
        'wait': "⏳ Data received! Please wait...",
        'buy': "💎 **Buy Premium**\nKPay: `09695616591` (3000 MMK)",
        'no_yt': "❌ YouTube is not supported."
    }
}

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="setlang_my"),
        InlineKeyboardButton("🇺🇸 English", callback_data="setlang_en")
    ]])
    await message.reply_text("Choose Language / ဘာသာစကားရွေးပါ။", reply_markup=kb)

@app.on_callback_query(filters.regex("^setlang_"))
async def set_lang(client, callback_query):
    lang = callback_query.data.split("_")[1]
    uid = str(callback_query.from_user.id)
    db.collection('users').document(uid).set({
        'lang': lang, 'is_premium': False, 'used_trial': False, 'expiry_date': None
    }, merge=True)
    await callback_query.edit_message_text(TEXTS[lang]['desc'])

@app.on_message((filters.video | filters.text) & filters.private)
async def handle_input(client, message):
    uid = str(message.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict()
    if not u_doc: return
    lang = u_doc.get('lang', 'my')

    # Premium Check
    if not u_doc.get('is_premium') and u_doc.get('used_trial'):
        await message.reply_text(TEXTS[lang]['buy'])
        return

    data = {}
    if message.video:
        data['type'] = 'video'
        # Forward ဗီဒီယိုဆိုရင် file_id က တစ်ခါတစ်လေ အလုပ်မလုပ်လို့ unique id ကိုပါ မှတ်မယ်
        data['val'] = message.video.file_id
    elif message.text:
        if message.text.startswith("/"): return
        links = re.findall(r'https?://[^\s]+', message.text)
        if not links: return
        if 'youtube' in links[0] or 'youtu.be' in links[0]:
            await message.reply_text(TEXTS[lang]['no_yt']); return
        data['type'] = 'link'; data['val'] = links[0]

    user_steps[uid] = {'step': 'name', 'data': data, 'lang': lang}
    await message.reply_text(TEXTS[lang]['ask_name'])

@app.on_message(filters.text & filters.private)
async def steps_handler(client, message):
    uid = str(message.from_user.id)
    if uid not in user_steps: return
    
    step, lang = user_steps[uid]['step'], user_steps[uid]['lang']
    val = message.text
    
    if step == 'name':
        user_steps[uid]['data']['name'] = "Movie" if val == "/skip" else val
        user_steps[uid]['step'] = 'len'
        await message.reply_text(TEXTS[lang]['ask_len'])
    elif step == 'len':
        user_steps[uid]['data']['len'] = 5 if val == "/skip" else int(val)
        user_steps[uid]['step'] = 'wm'
        await message.reply_text(TEXTS[lang]['ask_wm'])
    elif step == 'wm':
        wm = "" if val == "/skip" else val
        d = user_steps[uid]['data']
        db.collection('tasks').add({
            'user_id': uid, 'type': d['type'], 'value': d['val'],
            'name': d['name'], 'len': d['len'], 'wm': wm, 'lang': lang,
            'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
        })
        db.collection('users').document(uid).update({'used_trial': True})
        await message.reply_text(TEXTS[lang]['wait'])
        del user_steps[uid]

app.run()
