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

# --- [Firebase Setup with Error Handling] ---
db = None
try:
    if not firebase_admin._apps:
        cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
            db = firestore.client()
        else:
            print("❌ FIREBASE_SERVICE_ACCOUNT is missing!")
except Exception as e:
    print(f"❌ Firebase Init Error: {e}")

app = Client("interface_bot", 
             api_id=int(os.environ.get("API_ID")), 
             api_hash=os.environ.get("API_HASH"), 
             bot_token=os.environ.get("TELEGRAM_TOKEN"))

# --- [Settings] ---
ADMIN_ID = 1715890141 
KPAY_NO = "09695616591"
USDT_ADDRESS = "0x56824c51be35937da7E60a6223E82cD1795984cC"

TEXTS = {
    'my': {
        'intro': (
            "🚀 **Professional Video Splitter Bot**\n\n"
            "✅ **Fast Splitting:** ဗီဒီယိုများကို မိနစ်အလိုက် အမြန်ဖြတ်ပေးခြင်း။\n"
            "✅ **Link Support:** Drive, TikTok, FB, Bilibili Link များရခြင်း။\n"
            "✅ **Watermark:** ကိုယ်ပိုင်စာသား Watermark ထည့်သွင်းပေးခြင်း။\n\n"
            "👇 **ဗီဒီယိုဖိုင် သို့မဟုတ် Link ပို့ပြီး စမ်းသပ်ကြည့်လိုက်ပါ!**"
        ),
        'ask_name': "📝 **Movie Name ပေးပါ** (ကျော်ရန် /skip)",
        'ask_len': "⏱ **ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ?** (ဥပမာ - 5)",
        'ask_wm': "📝 **Watermark စာသားပေးပါ** (ကျော်ရန် /skip)",
        'done': "⏳ **လက်ခံရရှိပါပြီ**။ အပိုင်းများ မကြာမီ ပြန်ပို့ပေးပါမည်။",
        'expired': (
            "⚠️ **သင့်ရဲ့ ၁ ရက် Trial သက်တမ်း ကုန်ဆုံးသွားပါပြီ**\n\n"
            "💰 **Premium:** ၃၀၀၀ ကျပ် / 1.0 USDT\n"
            f"💳 **KPay:** `{KPAY_NO}`\n"
            f"🌐 **USDT:** `{USDT_ADDRESS}`"
        )
    },
    'en': {
        'intro': "🚀 **Professional Video Splitter Bot**\n\nFast splitting and Watermark features.\n\n👇 **Send Video or Link!**",
        'ask_name': "📝 **Movie Name** (Or /skip)",
        'ask_len': "⏱ **Minutes per part?**",
        'ask_wm': "📝 **Watermark text?**",
        'done': "⏳ **Received!** Processing...",
        'expired': "⚠️ Your 1-day Trial has Expired!"
    }
}

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"),
        InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    ]])
    await m.reply_text("👋 **Welcome to Movie Spliter Bot**\nPlease select language.", reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang, uid = q.data.split("_")[1], str(q.from_user.id)
    if db:
        u_ref = db.collection('users').document(uid)
        if not u_ref.get().exists:
            u_ref.set({'lang': lang, 'expiry_date': (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), 'step': 'idle'})
        else:
            u_ref.update({'lang': lang, 'step': 'idle'})
    await q.edit_message_text(TEXTS[lang]['intro'])

@app.on_message(filters.private)
async def main_handler(c, m):
    if not db: return
    uid = str(m.from_user.id)
    u_ref = db.collection('users').document(uid)
    u_snap = u_ref.get()
    
    if not u_snap.exists: return
    u_doc = u_snap.to_dict()
    lang = u_doc.get('lang', 'my')
    step = u_doc.get('step', 'idle')

    # Expiry Check
    if datetime.now() > datetime.strptime(u_doc['expiry_date'], "%Y-%m-%d %H:%M:%S"):
        await m.reply_text(TEXTS[lang]['expired']); return

    # Media Check
    is_media = m.video or (m.document and "video" in m.document.mime_type)
    links = re.findall(r'https?://[^\s]+', m.text) if m.text else []

    if is_media or links:
        if m.text and m.text.startswith("/"): return
        val = m.video.file_id if m.video else (m.document.file_id if m.document else links[0])
        u_ref.update({'step': 'name', 'temp_data': {'type': 'video' if is_media else 'link', 'val': val}})
        await m.reply_text(TEXTS[lang]['ask_name'])
        return

    # Step Logic
    if m.text and step != 'idle':
        data = u_doc.get('temp_data', {})
        if step == 'name':
            data['name'] = "Movie" if m.text == "/skip" else m.text
            u_ref.update({'step': 'len', 'temp_data': data})
            await m.reply_text(TEXTS[lang]['ask_len'])
        elif step == 'len':
            try:
                data['len'] = 5 if m.text == "/skip" else int(m.text)
                u_ref.update({'step': 'wm', 'temp_data': data})
                await m.reply_text(TEXTS[lang]['ask_wm'])
            except: await m.reply_text("ဂဏန်းရိုက်ပါ")
        elif step == 'wm':
            wm = "" if m.text == "/skip" else m.text
            db.collection('tasks').add({
                'user_id': uid, 'type': data['type'], 'value': data['val'],
                'name': data['name'], 'len': data['len'], 'wm': wm,
                'lang': lang, 'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
            })
            u_ref.update({'step': 'idle', 'temp_data': {}})
            await m.reply_text(TEXTS[lang]['done'])

app.run()
