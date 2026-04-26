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

# --- [Admin & Settings] ---
ADMIN_ID = 1715890141 
KPAY_NO = "09695616591"
AYAPAY_NO = "09695616591"
USDT_ADDRESS = "0x56824c51be35937da7E60a6223E82cD1795984cC"

TEXTS = {
    'my': {
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
        'intro': "🚀 **Professional Video Splitter Bot**\n\nHigh-speed splitting, Link support, and Watermark features.\n\n👇 **Send a Video or Link now to try!**",
        'ask_name': "📝 **Enter Movie Name** (Or /skip)",
        'ask_len': "⏱ **Minutes per part?** (Example: 5)",
        'ask_wm': "📝 **Enter Watermark** (Or /skip)",
        'done': "⏳ **Received!** Processing...",
        'expired': "⚠️ **Your 1-day Trial has Expired!**\nPlease buy Premium to continue."
    }
}

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"), InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")]])
    await m.reply_text("👋 **Welcome!** Please select language:", reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang, uid = q.data.split("_")[1], str(q.from_user.id)
    u_ref = db.collection('users').document(uid)
    if not u_ref.get().exists:
        u_ref.set({'lang': lang, 'expiry_date': (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), 'step': 'idle'})
    else:
        u_ref.update({'lang': lang, 'step': 'idle'})
    await q.edit_message_text(TEXTS[lang]['intro'])

@app.on_message(filters.photo & filters.private)
async def handle_ss(c, m):
    await m.forward(ADMIN_ID)
    await c.send_message(ADMIN_ID, f"💰 **Payment SS**\nFrom UID: `{m.from_user.id}`")
    await m.reply_text("✅ Screenshot လက်ခံရရှိပါသည်။ စစ်ဆေးပြီးပါက သက်တမ်းတိုးပေးပါမည်။")

# --- [အဓိက Logic အပိုင်း: ရှေ့ဆက်မတက်တဲ့ပြဿနာကို ဒီမှာ ရှင်းထားပါတယ်] ---
@app.on_message(filters.private)
async def main_handler(c, m):
    uid = str(m.from_user.id)
    u_ref = db.collection('users').document(uid)
    u_doc_snap = u_ref.get()
    
    if not u_doc_snap.exists: return
    u_doc = u_doc_snap.to_dict()
    lang = u_doc.get('lang', 'my')
    step = u_doc.get('step', 'idle')

    # ၁။ Expiry စစ်မည် (၂၄ နာရီပြည့်မှ ငွေတောင်းမည်)
    if datetime.now() > datetime.strptime(u_doc['expiry_date'], "%Y-%m-%d %H:%M:%S"):
        await m.reply_text(TEXTS[lang]['expired'])
        return

    # ၂။ ဗီဒီယို သို့မဟုတ် Link ပို့လာလျှင်
    if m.video or (m.document and "video" in m.document.mime_type) or (m.text and re.findall(r'https?://[^\s]+', m.text)):
        if m.text and m.text.startswith("/"): return # Command တွေကို ကျော်မည်
        
        val = m.video.file_id if m.video else (m.document.file_id if m.document else re.findall(r'https?://[^\s]+', m.text)[0])
        u_ref.update({
            'step': 'name',
            'temp_data': {'type': 'video' if not m.text else 'link', 'val': val}
        })
        await m.reply_text(TEXTS[lang]['ask_name'])
        return

    # ၃။ Step-by-Step စာသားများ (နာမည်၊ မိနစ်၊ Watermark)
    if m.text:
        if step == 'name':
            data = u_doc.get('temp_data', {})
            data['name'] = "Movie" if m.text == "/skip" else m.text
            u_ref.update({'step': 'len', 'temp_data': data})
            await m.reply_text(TEXTS[lang]['ask_len'])

        elif step == 'len':
            try:
                data = u_doc.get('temp_data', {})
                data['len'] = 5 if m.text == "/skip" else int(m.text)
                u_ref.update({'step': 'wm', 'temp_data': data})
                await m.reply_text(TEXTS[lang]['ask_wm'])
            except:
                await m.reply_text("⚠️ ဂဏန်းပဲ ရိုက်ပေးပါ / Please enter numbers only.")

        elif step == 'wm':
            data = u_doc.get('temp_data', {})
            wm = "" if m.text == "/skip" else m.text
            db.collection('tasks').add({
                'user_id': uid, 'type': data['type'], 'value': data['val'],
                'name': data['name'], 'len': data['len'], 'wm': wm,
                'lang': lang, 'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
            })
            u_ref.update({'step': 'idle', 'temp_data': {}})
            await m.reply_text(TEXTS[lang]['done'])

app.run()
