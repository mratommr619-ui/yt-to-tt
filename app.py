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
    except Exception as e:
        print(f"Firebase Init Error: {e}")
db = firestore.client()

app = Client("interface_bot", 
             api_id=int(os.environ.get("API_ID")), 
             api_hash=os.environ.get("API_HASH"), 
             bot_token=os.environ.get("TELEGRAM_TOKEN"))

# --- [Admin & Payment Settings] ---
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
            "✅ **Fast Splitting:** ဗီဒီယိုအရှည်ကြီးတွေကို မိနစ်အလိုက် စက္ကန့်ပိုင်းအတွင်း ဖြတ်ပေးခြင်း။\n"
            "✅ **Link Support:** Drive, Bilibili, Facebook, TikTok Link တွေကို တိုက်ရိုက်ဒေါင်းပြီး အပိုင်းဖြတ်ပေးခြင်း။\n"
            "✅ **Watermark:** သင့်ကိုယ်ပိုင် Logo သို့မဟုတ် စာသားကို ဗီဒီယိုမှာ ထည့်သွင်းပေးခြင်း။\n"
            "✅ **HD Quality:** ဗီဒီယို အရည်အသွေး မကျဘဲ အပိုင်းများ ခွဲပေးခြင်း။\n\n"
            "👇 **အခုပဲ ဗီဒီယိုဖိုင် (သို့) Link တစ်ခုခု ပို့ပြီး စမ်းသပ်ကြည့်လိုက်ပါ!**"
        ),
        'ask_name': "📝 **Movie Name ပေးပါ** (ကျော်ရန် /skip)",
        'ask_len': "⏱ **ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ?** (ဂဏန်းပဲရိုက်ပါ ဥပမာ - 5)",
        'ask_wm': "📝 **Watermark စာသားပေးပါ** (ကျော်ရန် /skip)",
        'done': "⏳ **လက်ခံရရှိပါပြီ**။ အပိုင်းများ မကြာမီ ပြန်ပို့ပေးပါမည်။",
        'expired': (
            "⚠️ **သင့်ရဲ့ Free Trial ၂၄ နာရီ သက်တမ်း ကုန်ဆုံးသွားပါပြီ**\n\n"
            "ဆက်လက်အသုံးပြုလိုပါက Premium ဝယ်ယူနိုင်ပါတယ်။\n\n"
            "💰 **Premium Price:** ၃၀၀၀ ကျပ် / 1.0 USDT\n\n"
            f"💳 **KPay/AYA:** `{KPAY_NO}`\n"
            f"🌐 **USDT (TRC20):** `{USDT_ADDRESS}`\n\n"
            "ငွေလွှဲပြီး Screenshot ပုံကို ဒီထဲ တိုက်ရိုက်ပို့ပေးပါ။"
        )
    },
    'en': {
        'start': "👋 **Welcome to Movie Spliter Bot**\n\nPlease select your language to continue.",
        'intro': (
            "🚀 **Professional Video Splitter Bot**\n\n"
            "✅ **Fast Splitting:** Split long videos in seconds.\n"
            "✅ **Link Support:** Support Drive, Bilibili, FB, TikTok links.\n"
            "✅ **Watermark:** Add custom text watermark easily.\n"
            "✅ **High Quality:** No quality loss during processing.\n\n"
            "👇 **Send a Video or Link now to try!**"
        ),
        'ask_name': "📝 **Enter Movie Name** (Or /skip)",
        'ask_len': "⏱ **Minutes per part?** (Example: 5)",
        'ask_wm': "📝 **Enter Watermark** (Or /skip)",
        'done': "⏳ **Received!** Processing your video...",
        'expired': "⚠️ **Free Trial Expired!** Upgrade to Premium for 3000 MMK / 1.0 USDT."
    }
}

user_steps = {}

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"),
        InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    ]])
    await m.reply_text(TEXTS['my']['start'], reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang = q.data.split("_")[1]
    uid = str(q.from_user.id)
    u_ref = db.collection('users').document(uid)
    if not u_ref.get().exists:
        expiry = datetime.now() + timedelta(days=1)
        u_ref.set({'lang': lang, 'expiry_date': expiry.strftime("%Y-%m-%d %H:%M:%S")})
    else:
        u_ref.update({'lang': lang})
    await q.edit_message_text(TEXTS[lang]['intro'])

@app.on_message(filters.photo & filters.private)
async def handle_ss(c, m):
    await m.forward(ADMIN_ID)
    await c.send_message(ADMIN_ID, f"💰 **Payment Received**\nUID: `{m.from_user.id}`\nUser: @{m.from_user.username}")
    await m.reply_text("✅ Screenshot လက်ခံရရှိပါသည်။ Admin စစ်ဆေးပြီး သက်တမ်းတိုးပေးပါမည်။")

@app.on_message((filters.video | filters.text) & filters.private)
async def handle_input(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict()
    if not u_doc: return
    lang = u_doc.get('lang', 'my')

    # Expiry Check
    if datetime.now() > datetime.strptime(u_doc['expiry_date'], "%Y-%m-%d %H:%M:%S"):
        await m.reply_text(TEXTS[lang]['expired'])
        return

    if m.video:
        data = {'type': 'video', 'val': m.video.file_id}
    elif m.text:
        if m.text.startswith("/"): return
        links = re.findall(r'https?://[^\s]+', m.text)
        if not links or any(x in links[0] for x in ['youtube', 'youtu.be']): return
        data = {'type': 'link', 'val': links[0]}
    else: return

    user_steps[uid] = {'step': 'name', 'data': data, 'lang': lang}
    await m.reply_text(TEXTS[lang]['ask_name'])

@app.on_message(filters.text & filters.private)
async def steps_handler(c, m):
    uid = str(m.from_user.id)
    if uid not in user_steps: return
    
    curr = user_steps[uid]
    step = curr['step']
    lang = curr['lang']
    
    if step == 'name':
        user_steps[uid]['data']['name'] = "Movie" if m.text == "/skip" else m.text
        user_steps[uid]['step'] = 'len'
        await m.reply_text(TEXTS[lang]['ask_len'])
    elif step == 'len':
        try:
            val = 5 if m.text == "/skip" else int(m.text)
            user_steps[uid]['data']['len'] = val
            user_steps[uid]['step'] = 'wm'
            await m.reply_text(TEXTS[lang]['ask_wm'])
        except:
            await m.reply_text("ဂဏန်းပဲရိုက်ပါ / Enter numbers only.")
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
