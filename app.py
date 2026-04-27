import os, json, re, http.server, threading, time, requests
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

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
db = None
try:
    if not firebase_admin._apps:
        cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
            db = firestore.client()
except Exception as e: print(f"Firebase Error: {e}")

app = Client("interface_bot", api_id=int(os.environ.get("API_ID")), api_hash=os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN"))

# --- [Settings & Payments] ---
ADMIN_ID = 1715890141 
KPAY_NO = "09695616591"
AYAPAY_NO = "09695616591"
USDT_ADDRESS = "0x56824c51be35937da7E60a6223E82cD1795984cC"
PRICE_MMK = "3000 ကျပ်"
PRICE_USDT = "1.0 USDT"

TEXTS = {
    'my': {
        'start': "👋 **မင်္ဂလာပါ Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'intro': (
            "🚀 **Professional Video Splitter Bot**\n\n"
            "✅ **Fast Splitting:** ဗီဒီယိုများကို မိနစ်အလိုက် အမြန်ဖြတ်ပေးခြင်း။\n"
            "🔗 **Link Support:** Drive, TikTok, FB, Bilibili Link များကို တိုက်ရိုက်ဒေါင်းပေးခြင်း။\n"
            "📝 **Marquee Watermark:** စခရင်အနှံ့ ပတ်ပြေးနေသော Watermark ထည့်သွင်းပေးခြင်း။\n\n"
            "👇 **ဗီဒီယိုဖိုင် (သို့) Link တစ်ခုခု ပို့ပြီး စမ်းသပ်ကြည့်ပါ!**"
        ),
        'profile': "👤 **ကျွန်ုပ်၏ ပရိုဖိုင်**\n\n🆔 **User ID:** `{uid}`\n🌟 **အဆင့်:** {status}\n📅 **သက်တမ်းကုန်ဆုံးရက်:** `{exp}`",
        'expired': (
            "⚠️ **သင့်ရဲ့ Trial (သို့) Premium သက်တမ်း ကုန်ဆုံးသွားပါပြီ**\n\n"
            "ဆက်လက်အသုံးပြုလိုပါက Premium ဝယ်ယူနိုင်ပါတယ်။\n\n"
            f"💰 **၁ လ ဈေးနှုန်း:** {PRICE_MMK} / {PRICE_USDT}\n"
            f"💳 **KPay:** `{KPAY_NO}`\n"
            f"💳 **AYAPay:** `{AYAPAY_NO}`\n"
            f"🌐 **USDT (TRC20):** `{USDT_ADDRESS}`\n\n"
            "⚠️ **အရေးကြီး:** ငွေလွှဲရည်ညွှန်းချက် (Note) တွင် သင့် ID `{uid}` ကို ထည့်သွင်းပေးပါ။\n\n"
            "✅ ငွေလွှဲပြီးပါက Screenshot ပို့ပေးပါ။"
        ),
        'ask_name': "📝 **Movie Name ပေးပါ** (ကျော်ရန် /skip)",
        'ask_len': "⏱ **ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ?** (ဥပမာ - 5)",
        'ask_wm': "📝 **Watermark စာသားပေးပါ** (ကျော်ရန် /skip)",
        'done': "⏳ **လက်ခံရရှိပါပြီ**။ အပိုင်းများ မကြာမီ ပြန်ပို့ပေးပါမည်။"
    },
    'en': {
        'start': "👋 **Welcome to Movie Spliter Bot**",
        'intro': (
            "🚀 **Professional Video Splitter Bot**\n\n"
            "✅ **Fast Splitting:** Cut videos into parts instantly.\n"
            "🔗 **Link Support:** Drive, TikTok, FB, Bilibili direct download.\n"
            "📝 **Marquee Watermark:** Moving watermark across the screen.\n\n"
            "👇 **Send a Video or Link now!**"
        ),
        'profile': "👤 **My Profile**\n\n🆔 **User ID:** `{uid}`\n🌟 **Status:** {status}\n📅 **Expiry Date:** `{exp}`",
        'expired': (
            "⚠️ **Your Trial or Premium membership has expired!**\n\n"
            "Upgrade to Premium to continue.\n\n"
            f"💰 **Price:** {PRICE_MMK} / {PRICE_USDT}\n"
            f"💳 **KPay:** `{KPAY_NO}`\n"
            f"💳 **AYAPay:** `{AYAPAY_NO}`\n"
            f"🌐 **USDT (TRC20):** `{USDT_ADDRESS}`\n\n"
            "⚠️ **IMPORTANT:** Include your ID `{uid}` in payment note.\n\n"
            "✅ Send a Screenshot after payment."
        ),
        'ask_name': "📝 **Enter Movie Name** (Or /skip)",
        'ask_len': "⏱ **Minutes per part?**",
        'ask_wm': "📝 **Enter Watermark** (Or /skip)",
        'done': "⏳ **Received!** Processing..."
    }
}

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"),
        InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    ]])
    await m.reply_text(TEXTS['my']['start'], reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang, uid = q.data.split("_")[1], str(q.from_user.id)
    u_ref = db.collection('users').document(uid)
    expiry = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    if not u_ref.get().exists:
        u_ref.set({'lang': lang, 'expiry_date': expiry, 'step': 'idle', 'is_premium': False})
    else: u_ref.update({'lang': lang, 'step': 'idle'})
    
    p_text = "👤 My Profile" if lang == 'en' else "👤 ကျွန်ုပ်၏ ပရိုဖိုင်"
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=ReplyKeyboardMarkup([[p_text]], resize_keyboard=True))

@app.on_message(filters.regex("^(👤 My Profile|👤 ကျွန်ုပ်၏ ပရိုဖိုင်)") & filters.private)
async def my_profile(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict()
    lang = u_doc.get('lang', 'my')
    status = "Premium 🌟" if u_doc.get('is_premium') else "Trial Member"
    await m.reply_text(TEXTS[lang]['profile'].format(uid=uid, status=status, exp=u_doc['expiry_date']))

@app.on_message(filters.photo & filters.private)
async def handle_ss(c, m):
    await m.forward(ADMIN_ID)
    await c.send_message(ADMIN_ID, f"💰 **Payment SS from UID:** `{m.from_user.id}`")
    await m.reply_text("✅ Screenshot လက်ခံရရှိပါသည်။ / Received.")

@app.on_message(filters.private)
async def main_handler(c, m):
    if not db or not m.from_user: return
    uid = str(m.from_user.id)
    u_ref = db.collection('users').document(uid)
    u_snap = u_ref.get()
    if not u_snap.exists: return
    u_doc = u_snap.to_dict()
    lang, step = u_doc.get('lang', 'my'), u_doc.get('step', 'idle')

    if datetime.now() > datetime.strptime(u_doc['expiry_date'], "%Y-%m-%d %H:%M:%S"):
        await m.reply_text(TEXTS[lang]['expired'].format(uid=uid)); return

    is_media = m.video or (m.document and m.document.mime_type and "video" in m.document.mime_type)
    link = re.findall(r'https?://[^\s]+', m.text)[0] if m.text and re.findall(r'https?://[^\s]+', m.text) else None

    if (is_media or link) and not (m.text and m.text.startswith("/")):
        val = m.video.file_id if m.video else (m.document.file_id if m.document else link)
        u_ref.update({'step': 'name', 'temp_type': 'video' if is_media else 'link', 'temp_val': val})
        await m.reply_text(TEXTS[lang]['ask_name'])
        return

    if m.text and step != 'idle':
        if step == 'name':
            u_ref.update({'temp_name': "Movie" if m.text == "/skip" else m.text, 'step': 'len'})
            await m.reply_text(TEXTS[lang]['ask_len'])
        elif step == 'len':
            try:
                u_ref.update({'temp_len': 5 if m.text == "/skip" else int(m.text), 'step': 'wm'})
                await m.reply_text(TEXTS[lang]['ask_wm'])
            except: await m.reply_text("Numbers only / ဂဏန်းရိုက်ပါ")
        elif step == 'wm':
            wm = "" if m.text == "/skip" else m.text
            db.collection('tasks').add({
                'user_id': uid, 'type': u_doc['temp_type'], 'value': u_doc['temp_val'],
                'name': u_doc['temp_name'], 'len': u_doc['temp_len'], 'wm': wm,
                'status': 'pending', 'last_sent_index': -1, 'createdAt': firestore.SERVER_TIMESTAMP
            })
            u_ref.update({'step': 'idle'})
            await m.reply_text(TEXTS[lang]['done'])

app.run()
