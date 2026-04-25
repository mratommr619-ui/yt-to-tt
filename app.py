
import os, json, re
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
        'desc': "🎬 ဗီဒီယိုကို တိုက်ရိုက်ပို့ပါ (သို့မဟုတ်) Forward လုပ်ပါ။\n🔗 Website Link များ (YT, FB, TikTok, Bilibili, Drive) ကိုလည်း ပို့နိုင်ပါသည်။\n\n🎁 ပထမဆုံး ၁ ခု အခမဲ့။ 💎 ၁ လစာ ၃၀၀၀ ကျပ်။",
        'ask_name': "🎬 Movie Name - အမည်ပေးပါ (ကျော်ရန် Skip နှိပ်ပါ)",
        'ask_len': "⏱ Split Length - ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ? (Default 5 မိနစ်)",
        'ask_wm': "📝 Watermark - ဗီဒီယိုပေါ်ကစာသား (ကျော်ရန် Skip နှိပ်ပါ)",
        'wait': "⏳ အချက်အလက်များ လက်ခံရရှိပါပြီ။ ခေတ္တစောင့်ဆိုင်းပေးပါ၊ ပြီးပါက Bot မှ အလိုအလျောက် ပြန်ပို့ပေးပါမည်။",
        'buy': "💎 **Premium ဝယ်ယူရန် (၁ လစာ)**\nKPay: `09695616591` (၃၀၀၀ ကျပ်)\nဒုတိယတစ်ခုမှစ၍ ဝယ်ယူရန် လိုအပ်ပါသည်။",
        'skip': "⏩ ကျော်မည်"
    },
    'en': {
        'desc': "🎬 Upload/Forward Video or Paste Links (YT, FB, Drive, Bilibili, etc).\n\n🎁 1st video FREE. 💎 3000 MMK/Month.",
        'ask_name': "🎬 Movie Name? (Or press Skip)",
        'ask_len': "⏱ Minutes per part? (Default 5 mins)",
        'ask_wm': "📝 Watermark text? (Or press Skip)",
        'wait': "⏳ Data received! Processing your video. Please wait...",
        'buy': "💎 **Buy Premium (Monthly)**\nKPay: `09695616591` (3000 MMK)\nPremium required for next tasks.",
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
    if not u_ref.get().exists: u_ref.set({'lang': lang, 'is_premium': False, 'used_trial': False})
    else: u_ref.update({'lang': lang})
    await q.edit_message_text(TEXTS[lang]['desc'])

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    u_doc = db.collection('users').document(uid).get().to_dict()
    if not u_doc: return
    lang = u_doc.get('lang', 'my')

    if not u_doc.get('is_premium') and u_doc.get('used_trial'):
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

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text if update.message else "Video"
    lang = db.collection('users').document(str(update.effective_user.id)).get().to_dict().get('lang', 'my')
    btn = [[InlineKeyboardButton(TEXTS[lang]['skip'], callback_data='skip')]]
    msg = update.message or update.callback_query.message
    await msg.reply_text(TEXTS[lang]['ask_len'], reply_markup=InlineKeyboardMarkup(btn))
    return LENGTH

async def get_len(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['len'] = update.message.text if update.message else "5"
    lang = db.collection('users').document(str(update.effective_user.id)).get().to_dict().get('lang', 'my')
    btn = [[InlineKeyboardButton(TEXTS[lang]['skip'], callback_data='skip')]]
    msg = update.message or update.callback_query.message
    await msg.reply_text(TEXTS[lang]['ask_wm'], reply_markup=InlineKeyboardMarkup(btn))
    return WATERMARK

async def get_wm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wm = update.message.text if update.message and update.message.text.lower() != 'skip' else ""
    uid = str(update.effective_user.id)
    u_ref = db.collection('users').document(uid)
    u_data = u_ref.get().to_dict()
    
    db.collection('tasks').add({
        'user_id': uid, 'type': context.user_data['type'], 'value': context.user_data['val'],
        'name': context.user_data['name'], 'len': int(context.user_data['len']),
        'wm': wm, 'lang': u_data['lang'], 'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
    })
    if not u_data.get('is_premium'): u_ref.update({'used_trial': True})
    msg = update.message or update.callback_query.message
    await msg.reply_text(TEXTS[u_data['lang']]['wait'])
    return ConversationHandler.END

if __name__ == '__main__':
    app = Application.builder().token(os.environ.get('TELEGRAM_TOKEN')).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(set_lang, pattern='^setlang_'))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.VIDEO | filters.TEXT, handle_input)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name), CallbackQueryHandler(get_name, pattern='skip')],
            LENGTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_len), CallbackQueryHandler(get_len, pattern='skip')],
            WATERMARK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_wm), CallbackQueryHandler(get_wm, pattern='skip')],
        }, fallbacks=[]
    ))
    app.run_polling()
