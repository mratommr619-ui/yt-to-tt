import os, json, re, http.server, threading, time, requests
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- [Render Anti-Sleep Fix] ---
def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    while True:
        try:
            if url: requests.get(url)
        except: pass
        time.sleep(600)

def run_dummy_server():
    http.server.HTTPServer(('', int(os.environ.get("PORT", 8080))), 
    type('H', (http.server.SimpleHTTPRequestHandler,), {'do_GET': lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b"OK"))})).serve_forever()

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

# --- [Admin & Settings] ---
ADMIN_ID = 1715890141 
KPAY_NO = "09695616591"
USDT_ADDRESS = "0x56824c51be35937da7E60a6223E82cD1795984cC"

TEXTS = {
    'my': {
        'start': "👋 **မင်္ဂလာပါ Movie Spliter Bot မှ ကြိုဆိုပါတယ်**\n\nရှေ့ဆက်ရန် ဘာသာစကား ရွေးချယ်ပေးပါ။",
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
        'done': "⏳ **လက်ခံရရှိပါပြီ**။ အပိုင်းများ မကြာမီ ပြန်ပို့ပေးပါမည်။",
        'expired': (
            "⚠️ **သင့်ရဲ့ ၁ ရက် Trial သက်တမ်း ကုန်ဆုံးသွားပါပြီ**\n\n"
            "💰 **Premium Price:** ၃၀၀၀ ကျပ် / 1.0 USDT\n"
            f"💳 **KPay/AYA:** `{KPAY_NO}`\n"
            f"🌐 **USDT:** `{USDT_ADDRESS}`\n\n"
            "ငွေလွှဲပြီး Screenshot ပုံကို ပို့ပေးပါ။"
        )
    },
    'en': {
        'start': "👋 **Welcome!** Select language.",
        'intro': "🚀 **Professional Video Splitter Bot**\n\nHigh-speed splitting, Link support, and Watermark features.\n\n👇 **Send a Video or Link now!**",
        'ask_name': "📝 **Movie Name** (Or /skip)",
        'ask_len': "⏱ **Minutes per part?**",
        'ask_wm': "📝 **Watermark text?**",
        'done': "⏳ **Received!** Processing...",
        'expired': "⚠️ Trial Expired! Please pay to continue."
    }
}

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"), InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")]])
    await m.reply_text(TEXTS['my']['start'], reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    if not db: return
    lang, uid = q.data.split("_")[1], str(q.from_user.id)
    u_ref = db.collection('users').document(uid)
    if not u_ref.get().exists:
        u_ref.set({'lang': lang, 'expiry_date': (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), 'step': 'idle'})
    else: u_ref.update({'lang': lang, 'step': 'idle'})
    await q.edit_message_text(TEXTS[lang]['intro'])

@app.on_message(filters.private)
async def main_handler(c, m):
    if not db: return
    uid = str(m.from_user.id)
    u_ref = db.collection('users').document(uid)
    u_snap = u_ref.get()
    if not u_snap.exists: return
    u_doc = u_snap.to_dict()
    
    lang, step = u_doc.get('lang', 'my'), u_doc.get('step', 'idle')

    if datetime.now() > datetime.strptime(u_doc['expiry_date'], "%Y-%m-%d %H:%M:%S"):
        await m.reply_text(TEXTS[lang]['expired']); return

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
            except: await m.reply_text("ဂဏန်းရိုက်ပါ")
        elif step == 'wm':
            wm = "" if m.text == "/skip" else m.text
            db.collection('tasks').add({
                'user_id': uid, 'type': u_doc.get('temp_type'), 'value': u_doc.get('temp_val'),
                'name': u_doc.get('temp_name'), 'len': u_doc.get('temp_len'), 'wm': wm,
                'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
            })
            u_ref.update({'step': 'idle'})
            await m.reply_text(TEXTS[lang]['done'])

app.run()
