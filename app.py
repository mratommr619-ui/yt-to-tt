import os, json, re, http.server, threading
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- [Render Port Fix] ---
def run_dummy_server():
    server_address = ('', int(os.environ.get("PORT", 8080)))
    httpd = http.server.HTTPServer(server_address, http.server.SimpleHTTPRequestHandler)
    httpd.serve_forever()
threading.Thread(target=run_dummy_server, daemon=True).start()

# --- [Firebase Setup] ---
if not firebase_admin._apps:
    cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(cert_dict)
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- [Bot Setup] ---
app = Client("interface_bot", api_id=int(os.environ.get("API_ID")), 
             api_hash=os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN"))

user_steps = {}

TEXTS = {
    'my': {
        'desc': "🎬 ဗီဒီယိုပို့ပါ (သို့) Link (Drive, Bilibili, FB) ပို့ပါ။\n🎁 Trial: ၂၄ နာရီ အခမဲ့ သုံးနိုင်ပါသည်။\n💎 Premium: ၁ လစာ ၃၀၀၀ ကျပ်။",
        'ask_name': "🎬 Movie Name ပေးပါ (ကျော်ရန် /skip)",
        'ask_len': "⏱ ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ? (Default 5)",
        'ask_wm': "📝 Watermark စာသား (ကျော်ရန် /skip)",
        'wait': "⏳ လက်ခံရရှိပါပြီ။ ၅ မိနစ်အတွင်း အပိုင်းများ ပြန်ပို့ပေးပါမည်။",
        'buy': "💎 **သက်တမ်းကုန်ဆုံးသွားပါပြီ**\n\nဆက်လက်သုံးစွဲရန် Premium ဝယ်ယူပေးပါ။ (၁ လ - ၃၀၀၀ ကျပ်)\nKPay: `09695616591` (Thet Oo)",
        'no_yt': "❌ YouTube မရပါ။"
    },
    'en': {
        'desc': "🎬 Upload Video or Paste Link.\n🎁 Trial: 24 Hours FREE access.\n💎 Premium: 3000 MMK / Month.",
        'ask_name': "🎬 Enter Movie Name (Or /skip)",
        'ask_len': "⏱ Minutes per part? (Default 5)",
        'ask_wm': "📝 Watermark text (Or /skip)",
        'wait': "⏳ Received! Parts will be sent within 5 mins.",
        'buy': "💎 **Account Expired**\n\nPlease buy Premium to continue. (3000 MMK/Month).",
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
    u_ref = db.collection('users').document(uid)
    
    if not u_ref.get().exists:
        # Trial ကို ၂၄ နာရီ ပေးလိုက်မယ် (လက်ရှိအချိန် + ၁ ရက်)
        expiry = datetime.now() + timedelta(days=1)
        u_ref.set({
            'lang': lang, 
            'is_premium': False, 
            'expiry_date': expiry.strftime("%Y-%m-%d %H:%M:%S")
        })
    else:
        u_ref.update({'lang': lang})
    await callback_query.edit_message_text(TEXTS[lang]['desc'])

@app.on_message((filters.video | filters.text) & filters.private)
async def handle_input(client, message):
    uid = str(message.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict()
    if not u_doc: return
    lang = u_doc.get('lang', 'my')

    # --- [Expiry Check] ---
    exp_str = u_doc.get('expiry_date')
    if exp_str:
        expiry_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expiry_dt:
            await message.reply_text(TEXTS[lang]['buy'])
            return

    data = {}
    if message.video:
        data['type'], data['val'] = 'video', message.video.file_id
    elif message.text:
        if message.text.startswith("/"): return
        links = re.findall(r'https?://[^\s]+', message.text)
        if not links: return
        if 'youtube' in links[0] or 'youtu.be' in links[0]:
            await message.reply_text(TEXTS[lang]['no_yt']); return
        data['type'], data['val'] = 'link', links[0]
    else: return

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
        user_steps[uid]['step'] = 'len'; await message.reply_text(TEXTS[lang]['ask_len'])
    elif step == 'len':
        user_steps[uid]['data']['len'] = 5 if val == "/skip" else int(val)
        user_steps[uid]['step'] = 'wm'; await message.reply_text(TEXTS[lang]['ask_wm'])
    elif step == 'wm':
        wm = "" if val == "/skip" else val
        d = user_steps[uid]['data']
        db.collection('tasks').add({
            'user_id': uid, 'type': d['type'], 'value': d['val'],
            'name': d['name'], 'len': d['len'], 'wm': wm, 'lang': lang,
            'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
        })
        await message.reply_text(TEXTS[lang]['wait'])
        del user_steps[uid]

app.run()
