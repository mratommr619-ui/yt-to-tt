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
AYAPAY_NO = "09695616591"
USDT_ADDRESS = "0x56824c51be35937da7E60a6223E82cD1795984cC"

TEXTS = {
    'my': {
        'start': "👋 **မင်္ဂလာပါ Movie Spliter Bot မှ ကြိုဆိုပါတယ်**\n\nရှေ့ဆက်ရန် ဘာသာစကား ရွေးချယ်ပေးပါ။",
        'intro': (
            "🚀 **Professional Video Splitter Bot**\n\n"
            "ဒီ Bot က သင့်အတွက် ဘာတွေလုပ်ပေးနိုင်မလဲ?\n"
            "✅ **Fast Splitting:** ဗီဒီယိုအရှည်ကြီးတွေကို မိနစ်အလိုက် အမြန်ဆုံး ဖြတ်ပေးခြင်း။\n"
            "✅ **Link Support:** Drive, TikTok, FB, Bilibili Link များကို တိုက်ရိုက်ဒေါင်းပြီး အပိုင်းဖြတ်ပေးခြင်း။\n"
            "✅ **Watermark:** ကိုယ်ပိုင်စာသား Watermark ကို ဗီဒီယိုမှာ ထည့်သွင်းပေးခြင်း။\n"
            "✅ **HD Quality:** ဗီဒီယို အရည်အသွေး မကျဘဲ စနစ်တကျ အပိုင်းခွဲပေးခြင်း။\n\n"
            "👇 **အခုပဲ ဗီဒီယိုဖိုင် (သို့) Link တစ်ခုခု ပို့ပြီး စမ်းသပ်ကြည့်လိုက်ပါ!**"
        ),
        'ask_name': "📝 **Movie Name ပေးပါ** (ကျော်ရန် /skip)",
        'ask_len': "⏱ **ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ?** (ဥပမာ - 5)",
        'ask_wm': "📝 **Watermark စာသားပေးပါ** (ကျော်ရန် /skip)",
        'done': "⏳ **လက်ခံရရှိပါပြီ**။ အပိုင်းများ မကြာမီ ပြန်ပို့ပေးပါမည်။",
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
        'start': "👋 **Welcome!** Please select language.",
        'intro': (
            "🚀 **Professional Video Splitter Bot**\n\n"
            "✅ **Fast Splitting:** Cut long videos in seconds.\n"
            "✅ **Link Support:** Direct splitting from Drive, TikTok, FB links.\n"
            "✅ **Watermark:** Add custom watermark easily.\n\n"
            "👇 **Send a Video or Link now!**"
        ),
        'ask_name': "📝 **Enter Movie Name** (Or /skip)",
        'ask_len': "⏱ **Minutes per part?**",
        'ask_wm': "📝 **Enter Watermark** (Or /skip)",
        'done': "⏳ **Received!** Processing...",
        'expired': "⚠️ Your 1-day Trial has Expired! Upgrade to Premium."
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

@app.on_message(filters.photo & filters.private)
async def handle_ss(c, m):
    await m.forward(ADMIN_ID)
    await c.send_message(ADMIN_ID, f"💰 **Payment SS**\nFrom UID: `{m.from_user.id}`")
    await m.reply_text("✅ Screenshot လက်ခံရရှိပါသည်။ စစ်ဆေးပြီးပါက သက်တမ်းတိုးပေးပါမည်။")

@app.on_message(filters.private)
async def main_handler(c, m):
    if not db: return
    uid = str(m.from_user.id)
    u_ref = db.collection('users').document(uid)
    u_snap = u_ref.get()
    if not u_snap.exists: return
    u_doc = u_snap.to_dict()
    
    lang, step = u_doc.get('lang', 'my'), u_doc.get('step', 'idle')

    # Expiry Check (၁ ရက်ပြည့်မှ ငွေတောင်းမည်)
    if datetime.now() > datetime.strptime(u_doc['expiry_date'], "%Y-%m-%d %H:%M:%S"):
        await m.reply_text(TEXTS[lang]['expired']); return

    # Media Check
    is_media = m.video or (m.document and m.document.mime_type and "video" in m.document.mime_type)
    link_match = re.findall(r'https?://[^\s]+', m.text) if m.text else []

    if (is_media or link_match) and not (m.text and m.text.startswith("/")):
        val = m.video.file_id if m.video else (m.document.file_id if m.document else link_match[0])
        u_ref.update({'step': 'name', 'temp_type': 'video' if is_media else 'link', 'temp_val': val})
        await m.reply_text(TEXTS[lang]['ask_name'])
        return

    # Step-by-Step Logic (Firestore ထဲတွင် အဆင့်ဆင့်မှတ်မည်)
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
            # Final Task ကို Database သို့ ပို့မည်
            db.collection('tasks').add({
                'user_id': uid, 'type': u_doc.get('temp_type'), 'value': u_doc.get('temp_val'),
                'name': u_doc.get('temp_name'), 'len': u_doc.get('temp_len'), 'wm': wm,
                'lang': lang, 'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
            })
            u_ref.update({'step': 'idle'})
            await m.reply_text(TEXTS[lang]['done'])

app.run()
