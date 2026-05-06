import os, json, threading, http.server, time, requests, urllib.parse
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

# --- [ Configuration ] ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEB_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app/")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "") 

ADMIN_ID = 1715890141
KPAY, AYAPAY, BEP20 = "09695616591", "09695616591", "0x56824c51be35937da7E60a6223E82cD1795984cC"

if not firebase_admin._apps:
    cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
    if cred_json: firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()
app = Client("luxury_spliter_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- [ Survival Logic ] ---
def run_health_server():
    port = int(os.getenv("PORT", 8080))
    httpd = http.server.HTTPServer(('', port), http.server.SimpleHTTPRequestHandler)
    httpd.serve_forever()

def self_ping():
    if not RENDER_URL: return
    while True:
        try:
            time.sleep(600)
            requests.get(RENDER_URL)
        except: pass

# --- [ UI Texts - Enhanced ] ---
TEXTS = {
    'my': {
        'intro': "👑 **Luxury Movie Spliter Pro မှ ကြိုဆိုပါတယ်** 👑\n\n🚀 **Bot စွမ်းဆောင်ရည်များ**\n• ဗီဒီယိုများကို အပိုင်းအလိုက် အမြန်ဖြတ်ပေးခြင်း\n• ကိုယ်ပိုင် Logo နှင့် ရေလှိုင်း Watermark များထည့်ခြင်း\n• TikTok/FB အတွက် အကောင်းဆုံး Branding Tool\n\n💎 **Premium အကျိုးကျေးဇူး**\n• Bot Watermark များ လုံးဝမပါတော့ခြင်း\n• Mini App တွင် ကြော်ငြာများ ပိတ်သွားခြင်း\n• ဦးစားပေးစနစ်ဖြင့် ပိုမိုမြန်ဆန်လာခြင်း",
        'open': "🚀 Mini App ဖွင့်ရန်", 'profile': "👤 My Profile", 'buy': "💎 Premium ဝယ်ရန်", 'refer': "👥 Refer Link",
        'payment': "💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.0 USDT\n💳 **KPay:** `{kpay}`\n💳 **AYAPay:** `{ayapay}`\n🌐 **BEP20:** `{bep20}`\n⚠️ **Note:** ID `{uid}` ကို Screenshot နှင့်အတူ ပို့ပေးပါ။",
        'forward_msg': "✅ **ဗီဒီယိုကို မှတ်မိပါသည်။**\n🔗 လင့်ခ်ကို ကူးယူပါ:\n`{v_link}`",
        'ack': "ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။"
    },
    'en': {
        'intro': "👑 **Welcome to Luxury Movie Spliter Pro** 👑\n\n🚀 **Bot Features**\n• Split long videos into custom parts\n• Add custom Logo & Wave Watermarks\n• High-speed processing & branding\n\n💎 **Premium Benefits**\n• No Bot Watermarks\n• Ad-free Mini App experience\n• Priority processing queue",
        'open': "🚀 Open Mini App", 'profile': "👤 My Profile", 'buy': "💎 Buy Premium", 'refer': "👥 Refer Link",
        'payment': "💎 **Premium Upgrade**\n\n💰 **1 Month:** 3000 MMK / 1.0 USDT\n💳 **KPay:** `{kpay}`\n💳 **AYAPay:** `{ayapay}`\n🌐 **BEP20:** `{bep20}`\n⚠️ **Note:** Please send screenshot with ID `{uid}`.",
        'forward_msg': "✅ **Video recognized!**\n🔗 Tap to copy link:\n`{v_link}`",
        'ack': "Video received! Processing..."
    }
}

def get_main_kb(lang):
    return ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=WEB_URL))],
        [KeyboardButton(TEXTS[lang]['profile']), KeyboardButton(TEXTS[lang]['refer'])],
        [KeyboardButton(TEXTS[lang]['buy'])]
    ], resize_keyboard=True)

# --- [ Listeners ] ---
def ack_listener():
    while True:
        try:
            pendings = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).get()
            for p in pendings:
                data = p.to_dict()
                uid, lang = int(data.get('user_id', 0)), data.get('lang', 'my')
                app.send_message(uid, TEXTS[lang]['ack'], reply_markup=get_main_kb(lang))
                p.reference.update({'status': 'queued'})
            time.sleep(5)
        except: time.sleep(10)

# --- [ Handlers ] ---

@app.on_message(filters.command("start") & filters.private)
async def start(c, m):
    uid, args = str(m.from_user.id), m.text.split()
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()

    if not user_doc.exists and len(args) > 1:
        inviter_id = args[1]
        if inviter_id != uid:
            inv_ref = db.collection('users').document(inviter_id)
            inv_doc = inv_ref.get()
            if inv_doc.exists:
                inv_data = inv_doc.to_dict()
                new_count = inv_data.get('referral_count', 0) + 1
                inv_lang = inv_data.get('lang', 'my')
                
                # ✅ ၅ ယောက်မြောက်တိုင်း Reward ပေးခြင်း (Count ကို Reset မလုပ်ပါ)
                if new_count % 5 == 0:
                    curr_expiry = inv_data.get('expiry_date', 'N/A')
                    target_start = datetime.now()
                    if curr_expiry != 'N/A':
                        try:
                            old_date = datetime.strptime(curr_expiry, "%Y-%m-%d %H:%M:%S")
                            if old_date > target_start: target_start = old_date
                        except: pass
                    new_expiry = (target_start + timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
                    
                    inv_ref.update({'is_premium': True, 'expiry_date': new_expiry, 'referral_count': new_count})
                    
                    msg = "🎊 ဂုဏ်ယူပါတယ်! Referral ၅ ယောက်ပြည့်သဖြင့် Premium ၁၀ ရက် လက်ဆောင်ရပါပြီ။" if inv_lang == 'my' else "🎊 Congratulations! 5 friends invited, you got 10 days Premium!"
                    try: await c.send_message(int(inviter_id), msg)
                    except: pass
                else:
                    inv_ref.update({'referral_count': new_count})

    if not user_doc.exists:
        user_ref.set({'lang': 'my', 'uid': uid, 'is_premium': False, 'expiry_date': 'N/A', 'referral_count': 0})

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data="lang_my"), InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")]])
    await m.reply_text("Choose Language / ဘာသာစကားရွေးချယ်ပါ -", reply_markup=kb)

@app.on_callback_query(filters.regex("^lang_"))
async def set_lang(c, q):
    lang = q.data.split("_")[1]
    uid = str(q.from_user.id)
    db.collection('users').document(uid).update({'lang': lang})
    await q.message.delete()
    await c.send_message(uid, TEXTS[lang]['intro'], reply_markup=get_main_kb(lang))

@app.on_message(filters.regex(r"(👤 My Profile|👤 Profile|👥 Refer Link)") & filters.private)
async def handle_profile_refer(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    count = u_doc.get('referral_count', 0)
    next_goal = ((count // 5) + 1) * 5
    bot_me = await c.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start={uid}"
    status = "Premium ✅" if u_doc.get('is_premium') else "Free ❌"
    
    if "Refer" in m.text or "👥" in m.text:
        msg = (f"👥 **Referral System**\n\n"
               f"သူငယ်ချင်း ၅ ယောက်ဖိတ်တိုင်း Premium ၁၀ ရက်ရပါမည်။\n\n"
               f"စုစုပေါင်းဖိတ်ပြီးသူ: `{count}` ယောက်\n"
               f"နောက်ထပ်လိုအပ်ချက်: `{next_goal - count}` ယောက်\n\n"
               f"🔗 လင့်ခ်:\n`{ref_link}`") if lang == 'my' else \
              (f"👥 **Referral System**\n\n"
               f"Invite 5 friends for 10 days Premium!\n\n"
               f"Total Invited: `{count}`\n"
               f"Next Reward at: `{next_goal}`\n\n"
               f"🔗 Link:\n`{ref_link}`")
        await m.reply_text(msg)
    else:
        await m.reply_text(f"👤 **Profile**\n🆔: `{uid}`\n👑: {status}\n📅: {u_doc.get('expiry_date','N/A')}\n👥 Total Refer: `{count}`", reply_markup=get_main_kb(lang))

@app.on_message((filters.video | filters.document) & filters.private & filters.incoming)
async def handle_video(c, m):
    if m.outgoing: return
    if m.document and m.document.file_size < 1048576: return
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    bot_info = await c.get_me()
    v_link = f"https://t.me/{bot_info.username}/{m.id}"
    encoded_link = urllib.parse.quote(v_link)
    caption = TEXTS[lang]['forward_msg'].format(v_link=v_link)
    inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton(TEXTS[lang]['open'], web_app=WebAppInfo(url=f"{WEB_URL}?link={encoded_link}"))]])
    await m.reply_text(caption, reply_markup=inline_kb)

@app.on_message((filters.photo | (filters.document & filters.private)))
async def handle_payment(c, m):
    if m.photo or (m.document and m.document.file_size < 2097152):
        uid = m.from_user.id
        await m.forward(ADMIN_ID)
        await c.send_message(ADMIN_ID, f"⬆️ **Payment Screenshot Above**\nUser ID: `{uid}`")
        u_doc = db.collection('users').document(str(uid)).get().to_dict() or {}
        lang = u_doc.get('lang', 'my')
        conf = "ငွေလွှဲပြေစာ ပို့ပြီးပါပြီ။ Admin မှ မကြာမီ စစ်ဆေးပေးပါမည်။" if lang == 'my' else "Payment sent! Admin will verify soon."
        await m.reply_text(conf)

@app.on_message(filters.regex(r"(💎 Premium ဝယ်ရန်|💎 Buy Premium)") & filters.private)
async def buy_premium(c, m):
    uid = str(m.from_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict() or {}
    lang = u_doc.get('lang', 'my')
    await m.reply_text(TEXTS[lang]['payment'].format(uid=uid, kpay=KPAY, ayapay=AYAPAY, bep20=BEP20))

if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()
    threading.Thread(target=ack_listener, daemon=True).start()
    app.run()
