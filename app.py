import os, json, re
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# --- Firebase Setup ---
cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(cert_dict)
if not firebase_admin._apps: firebase_admin.initialize_app(cred)
db = firestore.client()

NAME, LENGTH, WATERMARK = range(3)
URL_REG = r'https?://[^\s]+'

TEXTS = {
    'my': {
        'desc': "🎬 ဗီဒီယိုကို တိုက်ရိုက်ပို့ပါ (သို့) Forward လုပ်ပါ။\n🔗 Website Link များ (YT, FB, Drive, Bilibili) ပို့နိုင်ပါသည်။\n\n🎁 ပထမဆုံး ၁ ခု အခမဲ့။ 💎 ၁ လစာ ၃၀၀၀ ကျပ်။",
        'ask_name': "🎬 Movie Name - အမည်ပေးပါ (ကျော်ရန် Skip နှိပ်ပါ)",
        'ask_len': "⏱ Split Length - ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ? (Default 5)",
        'ask_wm': "📝 Watermark - စာသား (ကျော်ရန် Skip နှိပ်ပါ)",
        'wait': "⏳ လက်ခံရရှိပါပြီ။ ခေတ္တစောင့်ပေးပါ...",
        'buy': "💎 **Premium သက်တမ်းကုန်ဆုံးသွားပါပြီ**\n\nရှေ့ဆက်အသုံးပြုရန် (၁ လစာ ၃၀၀၀ ကျပ်) ထပ်မံဝယ်ယူပေးပါရန်။\nKPay: `09695616591` (Thet Oo)",
        'skip': "⏩ ကျော်မည်"
    },
    'en': {
        'desc': "🎬 Upload Video or Paste Links.\n🎁 1st video FREE. 💎 3000 MMK/Month.",
        'ask_name': "🎬 Movie Name? (Or Skip)",
        'ask_len': "⏱ Minutes per part? (Default 5)",
        'ask_wm': "📝 Watermark text? (Or Skip)",
        'wait': "⏳ Processing... please wait.",
        'buy': "💎 **Premium Expired**\n\nPlease renew for 3000 MMK/Month.",
        'skip': "⏩ Skip"
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data='setlang_my'), InlineKeyboardButton("🇺🇸 English", callback_data='setlang_en')]]
    await update.message.reply_text("Choose Language / ဘာသာစကားရွေးပါ။", reply_markup=InlineKeyboardMarkup(kb))

async def set_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    lang, uid = q.data.split('_')[1], str(q.from_user.id)
    u_ref = db.collection('users').document(uid)
    if not u_ref.get().exists:
        u_ref.set({'lang': lang, 'is_premium': False, 'used_trial': False, 'expiry_date': None})
    else:
        u_ref.update({'lang': lang})
    await q.edit_message_text(TEXTS[lang]['desc'])

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    u_ref = db.collection('users').document(uid)
    u_doc = u_ref.get().to_dict()
    if not u_doc: return
    lang = u_doc.get('lang', 'my')

    # --- [Premium & Expiry Check] ---
    is_pre = u_doc.get('is_premium', False)
    used_trial = u_doc.get('used_trial', False)
    exp_date = u_doc.get('expiry_date') # Firebase Timestamp or String

    if is_pre and exp_date:
        # လက်ရှိအချိန်နဲ့ နှိုင်းယှဉ်မယ်
        now = datetime.now()
        if isinstance(exp_date, str):
            exp_dt = datetime.strptime(exp_date, "%Y-%m-%d")
        else:
            exp_dt = exp_date # Firebase Timestamp automatically converts
            
        if now > exp_dt:
            # သက်တမ်းကုန်ပြီဖြစ်၍ Free ပြန်ပြောင်းမယ်
            u_ref.update({'is_premium': False, 'used_trial': True})
            is_pre = False

    if not is_pre and used_trial:
        await update.message.reply_text(TEXTS[lang]['buy'], parse_mode='Markdown')
        return ConversationHandler.END

    if update.message.video:
        context.user_data['type'], context.user_data['val'] = 'video', update.message.video.file_id
    elif update.message.text:
        link = re.findall(URL_REG, update.message.text)
        if not link: return
        context.user_data['type'], context.user_data['val'] = 'link', link[0]
    else: return

    btn = [[InlineKeyboardButton(TEXTS[lang]['skip'], callback_data='skip')]]
    await update.message.reply_text(TEXTS[lang]['ask_name'], reply_markup=InlineKeyboardMarkup(btn))
    return NAME

# (get_name, get_len, get_wm functions အရင်အတိုင်း - Code တိုအောင် မပြတော့ပါ)
# ... [အောက်ဆုံးမှာ အရင်အတိုင်း main run ရန်] ...
