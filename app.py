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

# --- [Admin & Payment] ---
ADMIN_ID = 1715890141 
KPAY_NO = "09695616591"
AYAPAY_NO = "09695616591"
USDT_ADDRESS = "0x56824c51be35937da7E60a6223E82cD1795984cC"

TEXTS = {
    'my': {
        'start': "👋 **မင်္ဂလာပါ Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'intro': (
            "🚀 **ဒီ Bot က ဘာတွေလုပ်ပေးနိုင်သလဲ?**\n\n"
            "🎬 **Video Splitting:** ဗီဒီယိုအရှည်ကြီးတွေကို မိနစ်အလိုက် စနစ်တကျ အပိုင်းဖြတ်ပေးခြင်း။\n"
            "🔗 **Link Support:** Drive, Bilibili, Facebook, TikTok Link တွေကို တိုက်ရိုက်ဒေါင်းပြီး အပိုင်းဖြတ်ပေးခြင်း။\n"
            "📝 **Watermark:** ကိုယ်ပိုင်စာသား Watermark များကို ဗီဒီယိုပေါ်တွင် ထည့်သွင်းပေးခြင်း။\n"
            "⚡ **High Speed:** အချိန်တိုအတွင်း အပိုင်းများကို အမြန်ဆုံးပြန်ပို့ပေးခြင်း။\n\n"
            "👇 **အခုပဲ ဗီဒီယိုဖိုင် (သို့) Link တစ်ခုခု ပို့ပြီး စမ်းသပ်ကြည့်လိုက်ပါ!**"
        ),
        'ask_name': "📝 **Movie Name ပေးပါ** (ကျော်ရန် /skip)",
        'ask_len': "⏱ **ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ?** (ဥပမာ - 5)",
        'ask_wm': "📝 **Watermark စာသားပေးပါ** (ကျော်ရန် /skip)",
        'done': "⏳ **လက်ခံရရှိပါပြီ**။ အပိုင်းများ ပြန်ပို့ပေးပါမည်။",
        'expired': (
            "⚠️ **သင့်ရဲ့ Free Trial သက်တမ်း ကုန်ဆုံးသွားပါပြီ**\n\n"
            "ဆက်လက်အသုံးပြုလိုပါက Premium ဝယ်ယူနိုင်ပါတယ်။\n\n"
            "💰 **Premium (၁ လစာ):** ၃၀၀၀ ကျပ် / 1.0 USDT\n\n"
            f"💳 **KPay/AYA:** `{KPAY_NO}`\n"
            f"🌐 **USDT (TRC20):** `{USDT_ADDRESS}`\n\n"
            "ငွေလွှဲပြီး Screenshot ပုံကို ဒီ Bot ထံ တိုက်ရိုက်ပို့ပေးပါ။"
        )
    },
    'en': {
        'start': "👋 **Welcome to Movie Spliter Bot**",
        'intro': (
            "🚀 **What can this Bot do?**\n\n"
            "🎬 **Video Splitting:** High-quality splitting by minutes.\n"
            "🔗 **Link Support:** Direct splitting from Drive, Bilibili, FB, TikTok links.\n"
            "📝 **Watermark:** Add custom watermark to your videos.\n"
            "⚡ **High Speed:** Fast processing and delivery.\n\n"
            "👇 **Send a Video or Link now to try it out!**"
        ),
        'ask_name': "📝 **Enter Movie Name** (Or /skip)",
        'ask_len': "⏱ **Minutes per part?** (Example: 5)",
        'ask_wm': "📝 **Enter Watermark** (Or /skip)",
        'done': "⏳ **Received!** Processing...",
        'expired': "⚠️ **Your Free Trial has Expired!**\n\nPlease upgrade to Premium.\nPrice: 3000 MMK / 1.0 USDT."
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
        # Trial ကို ၂၄ နာရီ တန်းပေးမည် (ငွေအကြောင်း မပြောသေး)
        expiry = datetime.now() + timedelta(days=1)
        u_ref.set({'lang': lang, 'expiry_date': expiry.strftime("%Y-%m-%d %H:%M:%S")})
    else: u_ref.update({'lang': lang})
    await q.edit_message_text(TEXTS[lang]['intro'])

@app.on_message(filters.photo & filters.private)
async def handle_ss(c, m):
    await m.forward(ADMIN_ID)
    await c.send_message(ADMIN_ID, f"💰 **Payment SS**\nUID: `{m.from_user.id}`\nUser: @{m.from_user.username}")
    await m.reply_text("✅ Screenshot လက်ခံရရှိပါသည်။ စစ်ဆေးပြီးပါက သက်တမ်းတိုးပေးပါမည်။")

@app.on_message((filters.video | filters.text) & filters.private)
async def handle_input(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict()
    if not u_doc: return
    lang = u_doc['lang']

    # ၂၄ နာရီ ပြည့်/မပြည့် စစ်ဆေးခြင်း
    if datetime.now() > datetime.strptime(u_doc['expiry_date'], "%Y-%m-%d %H:%M:%S"):
        await m.reply_text(TEXTS[lang]['expired']); return

    if m.video: data = {'type': 'video', 'val': m.video.file_id}
    elif m.text:
        if m.text.startswith("/"): return
        links = re.findall(r'https?://[^\s]+', m.text)
        if not links or "youtube" in links[0]: return
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
        try:
            user_steps[uid]['data']['len'] = 5 if m.text == "/skip" else int(m.text)
            user_steps[uid]['step'] = 'wm'
            await m.reply_text(TEXTS[lang]['ask_wm'])
        except: await m.reply_text("ဂဏန်းပဲရိုက်ပါ")
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
