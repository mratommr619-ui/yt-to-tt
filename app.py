import os, json, re, http.server, threading
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- [Render Port Fix] ---
def run_dummy_server():
    http.server.HTTPServer(('', int(os.environ.get("PORT", 8080))), 
    type('H', (http.server.SimpleHTTPRequestHandler,), {'do_GET': lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b"OK"))})).serve_forever()
threading.Thread(target=run_dummy_server, daemon=True).start()

# --- [Firebase Setup] ---
if not firebase_admin._apps:
    try:
        cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
        firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
    except Exception as e: print(f"Firebase Error: {e}")
db = firestore.client()

app = Client("interface_bot", api_id=int(os.environ.get("API_ID")), api_hash=os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN"))

# --- [Admin & Payments] ---
ADMIN_ID = 1715890141 
KPAY_NO = "09695616591"
AYAPAY_NO = "09695616591"
USDT_ADDRESS = "0x56824c51be35937da7E60a6223E82cD1795984cC"

user_states = {}

TEXTS = {
    'my': {
        'intro': (
            "🚀 **Professional Video Splitter Bot**\n\n"
            "ဒီ Bot က သင့်အတွက် ဘာတွေလုပ်ပေးနိုင်မလဲ?\n"
            "✅ **Fast Splitting:** ဗီဒီယိုအရှည်ကြီးတွေကို မိနစ်အလိုက် အမြန်ဆုံး ဖြတ်ပေးခြင်း။\n"
            "✅ **Link Support:** Drive, Bilibili, Facebook, TikTok Link တွေကို တိုက်ရိုက်ဒေါင်းပြီး အပိုင်းဖြတ်ပေးခြင်း။\n"
            "✅ **Watermark:** သင့်ကိုယ်ပိုင် စာသား/Logo ကို ဗီဒီယိုမှာ ထည့်သွင်းပေးခြင်း။\n"
            "✅ **HD Quality:** ဗီဒီယို အရည်အသွေး မကျဘဲ စနစ်တကျ အပိုင်းခွဲပေးခြင်း။\n\n"
            "👇 **အခုပဲ ဗီဒီယိုဖိုင် (သို့) Link တစ်ခုခု ပို့ပြီး စမ်းသပ်ကြည့်လိုက်ပါ!**"
        ),
        'ask_name': "📝 **Movie Name ပေးပါ** (ကျော်ရန် /skip)",
        'ask_len': "⏱ **ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ?** (ဥပမာ - 5)",
        'ask_wm': "📝 **Watermark စာသားပေးပါ** (ကျော်ရန် /skip)",
        'done': "⏳ **လက်ခံရရှိပါပြီ**။ အပိုင်းများ ပြန်ပို့ပေးပါမည်။",
        'expired': (
            "⚠️ **သင့်ရဲ့ ၁ ရက် Trial သက်တမ်း ကုန်ဆုံးသွားပါပြီ**\n\n"
            "ဆက်လက်အသုံးပြုလိုပါက Premium ဝယ်ယူနိုင်ပါတယ်။\n\n"
            "💰 **Premium Price:** ၃၀၀၀ ကျပ် / 1.0 USDT\n"
            f"💳 **KPay/AYA:** `{KPAY_NO}`\n"
            f"🌐 **USDT (TRC20):** `{USDT_ADDRESS}`\n\n"
            "ငွေလွှဲပြီး Screenshot ပုံကို ပို့ပေးပါ။"
        )
    },
    'en': {
        'intro': "🚀 **Professional Video Splitter Bot**\n\nHigh-speed splitting, Link support, and Watermark features.\n\n👇 **Send a Video or Link now!**",
        'ask_name': "📝 **Enter Movie Name** (Or /skip)",
        'ask_len': "⏱ **Minutes per part?** (Example: 5)",
        'ask_wm': "📝 **Enter Watermark** (Or /skip)",
        'done': "⏳ **Received!** Processing...",
        'expired': "⚠️ **Your 1-day Trial has Expired!**\n\nPlease buy Premium to continue."
    }
}

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"), InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")]])
    await m.reply_text("👋 **Welcome to Movie Spliter Bot**\nPlease select language.", reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang = q.data.split("_")[1]
    uid = str(q.from_user.id)
    u_ref = db.collection('users').document(uid)
    if not u_ref.get().exists:
        u_ref.set({'lang': lang, 'expiry_date': (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")})
    else: u_ref.update({'lang': lang})
    await q.edit_message_text(TEXTS[lang]['intro'])

@app.on_message(filters.photo & filters.private)
async def handle_ss(c, m):
    await m.forward(ADMIN_ID)
    await c.send_message(ADMIN_ID, f"💰 **Payment Screenshot**\nUID: `{m.from_user.id}`")
    await m.reply_text("✅ လက်ခံရရှိပါသည်။ စစ်ဆေးပြီးပါက သက်တမ်းတိုးပေးပါမည်။")

@app.on_message((filters.video | filters.document | filters.text) & filters.private)
async def handle_input(c, m):
    uid = str(m.from_user.id)
    u_doc_ref = db.collection('users').document(uid).get()
    if not u_doc_ref.exists: return

    u_doc = u_doc_ref.to_dict()
    lang = u_doc.get('lang', 'my')

    # --- [Exp Check: ၁ ရက်ကျော်မှ ငွေတောင်းမည့်နေရာ] ---
    if datetime.now() > datetime.strptime(u_doc['expiry_date'], "%Y-%m-%d %H:%M:%S"):
        await m.reply_text(TEXTS[lang]['expired']); return

    if m.video: data = {'type': 'video', 'val': m.video.file_id}
    elif m.document and "video" in m.document.mime_type: data = {'type': 'video', 'val': m.document.file_id}
    elif m.text:
        if m.text.startswith("/"): return
        links = re.findall(r'https?://[^\s]+', m.text)
        if not links or "youtube" in links[0]: return
        data = {'type': 'link', 'val': links[0]}
    else: return

    user_states[uid] = {'step': 'name', 'data': data, 'lang': lang}
    await m.reply_text(TEXTS[lang]['ask_name'])

@app.on_message(filters.text & filters.private)
async def steps_handler(c, m):
    uid = str(m.from_user.id)
    if uid not in user_states: return
    state = user_states[uid]
    step, lang = state['step'], state['lang']
    
    if step == 'name':
        user_states[uid]['data']['name'] = "Movie" if m.text == "/skip" else m.text
        user_states[uid]['step'] = 'len'; await m.reply_text(TEXTS[lang]['ask_len'])
    elif step == 'len':
        try:
            user_states[uid]['data']['len'] = 5 if m.text == "/skip" else int(m.text)
            user_states[uid]['step'] = 'wm'; await m.reply_text(TEXTS[lang]['ask_wm'])
        except: await m.reply_text("ဂဏန်းပဲရိုက်ပါ။")
    elif step == 'wm':
        wm = "" if m.text == "/skip" else m.text
        d = user_states[uid]['data']
        db.collection('tasks').add({
            'user_id': uid, 'type': d['type'], 'value': d['val'],
            'name': d['name'], 'len': d['len'], 'wm': wm, 'lang': lang,
            'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
        })
        await m.reply_text(TEXTS[lang]['done'])
        del user_states[uid]

app.run()
