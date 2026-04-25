import os
import json
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# --- [၁] Firebase Setup ---
cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(cert_dict)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

NAME, LENGTH, WATERMARK = range(3)

# --- [၂] Language & Texts ---
TEXTS = {
    'my': {
        'desc': "ဒီ Bot ဟာ ဗီဒီယိုတွေကို အပိုင်းဖြတ်ပေးပြီး Watermark ထည့်ပေးခြင်းဖြင့် လူကြီးမင်းတို့ရဲ့ အချိန်နဲ့ လူပင်ပန်းမှုကို သက်သာစေမှာပါ။\n\n💰 Premium ကြေး- ၁ လလျှင် ၃၀၀၀ ကျပ် (သို့မဟုတ်) $1 Crypto ပါ။\n✅ အသုံးပြုရန်အတွက် Premium ဝယ်ယူရန် လိုအပ်ပါသည်။",
        'ask_name': "🎬 Movie Name - ရုပ်ရှင်အမည်ကို ရိုက်ထည့်ပါ။ (ကျော်ရန် Skip နှိပ်ပါ)",
        'ask_len': "⏱ Video Split Length - ဘယ်နှစ်မိနစ်စီ ဖြတ်မလဲ? (Default 5 မိနစ်)",
        'ask_wm': "📝 Watermark - ဗီဒီယိုပေါ်မှာ ပေါ်စေချင်တဲ့စာကို ရိုက်ပါ။ (မထည့်လိုလျှင် Skip နှိပ်ပါ)",
        'done': "✅ လက်ခံရရှိပါပြီ။ ဗီဒီယိုဖြတ်ပြီးတာနဲ့ Bot ကနေ အလိုအလျောက် ပြန်ပို့ပေးပါ့မယ်။",
        'buy_info': "💎 **Premium ဝယ်ယူရန်**\n\n🇲🇲 မြန်မာငွေ - ၃၀၀၀ ကျပ်\nKPay / AYA Pay: `09695616591` (Thet Oo)\n\n🌐 Crypto - $1 (Any Crypto)\nBEP20: `0x56824c51be35937da7E60a6223E82cD1795984cC` (Copy and Pay)\n\nငွေလွှဲပြီးပါက Screenshot ကို Admin ထံ ပို့ပေးပါ။",
        'skip_btn': "⏩ ကျော်မည်",
        'status_btn': "📊 အခြေအနေ",
        'buy_btn': "💎 Premium ဝယ်ယူရန်",
    },
    'en': {
        'desc': "This bot saves your time by cutting videos and adding watermarks to prevent theft.\n\n💰 Premium- 3000 MMK or $1 Crypto per month.\n✅ Premium subscription is required to use the bot.",
        'ask_name': "🎬 Movie Name - Enter movie name. (Or press Skip)",
        'ask_len': "⏱ Video Split Length - Minutes per part? (Default 5 mins)",
        'ask_wm': "📝 Watermark - Enter text to show on video. (Or press Skip)",
        'done': "✅ Received! Parts will be sent automatically when finished.",
        'buy_info': "💎 **Buy Premium**\n\n🇲🇲 MMK - 3000 Kyats\nKPay / AYA Pay: `09695616591` (Thet Oo)\n\n🌐 Crypto - $1 (Any Crypto)\nBEP20: `0x56824c51be35937da7E60a6223E82cD1795984cC`\n\nPlease send payment screenshot to Admin.",
        'skip_btn': "⏩ Skip",
        'status_btn': "📊 Status",
        'buy_btn': "💎 Buy Premium",
    }
}

# --- [၃] Bot Logic ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇲🇲 မြန်မာစာ", callback_data='setlang_my'),
         InlineKeyboardButton("🇺🇸 English", callback_data='setlang_en')]
    ]
    await update.message.reply_text("Please choose your language / ဘာသာစကားရွေးချယ်ပါ။", reply_markup=InlineKeyboardMarkup(keyboard))

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = query.data.split('_')[1]
    user_id = str(query.from_user.id)
    db.collection('users').document(user_id).set({'lang': lang, 'is_premium': False}, merge=True)
    
    keyboard = [
        [InlineKeyboardButton(TEXTS[lang]['status_btn'], callback_data='status'),
         InlineKeyboardButton(TEXTS[lang]['buy_btn'], callback_data='buy')]
    ]
    await query.edit_message_text(TEXTS[lang]['desc'], reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    lang = db.collection('users').document(user_id).get().to_dict().get('lang', 'my')
    await query.edit_message_text(TEXTS[lang]['buy_info'], parse_mode='Markdown')

async def start_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data = db.collection('users').document(user_id).get().to_dict()
    if not user_data or not user_data.get('is_premium'):
        lang = user_data.get('lang', 'my') if user_data else 'my'
        await update.message.reply_text(TEXTS[lang]['buy_info'], parse_mode='Markdown')
        return ConversationHandler.END

    context.user_data['file_id'] = update.message.video.file_id
    lang = user_data.get('lang', 'my')
    btn = [[InlineKeyboardButton(TEXTS[lang]['skip_btn'], callback_data='skip')]]
    await update.message.reply_text(TEXTS[lang]['ask_name'], reply_markup=InlineKeyboardMarkup(btn))
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text if update.message else "Video"
    context.user_data['name'] = val
    user_id = str(update.effective_user.id)
    lang = db.collection('users').document(user_id).get().to_dict().get('lang', 'my')
    btn = [[InlineKeyboardButton(TEXTS[lang]['skip_btn'], callback_data='skip')]]
    msg = update.message if update.message else update.callback_query.message
    await msg.reply_text(TEXTS[lang]['ask_len'], reply_markup=InlineKeyboardMarkup(btn))
    return LENGTH

async def get_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text if update.message else "5"
    context.user_data['len'] = val
    user_id = str(update.effective_user.id)
    lang = db.collection('users').document(user_id).get().to_dict().get('lang', 'my')
    btn = [[InlineKeyboardButton(TEXTS[lang]['skip_btn'], callback_data='skip')]]
    msg = update.message if update.message else update.callback_query.message
    await msg.reply_text(TEXTS[lang]['ask_wm'], reply_markup=InlineKeyboardMarkup(btn))
    return WATERMARK

async def get_wm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text if update.message else ""
    wm = "" if val.lower() in ['no', 'skip', ''] else val
    user_id = str(update.effective_user.id)
    lang = db.collection('users').document(user_id).get().to_dict().get('lang', 'my')
    
    db.collection('tasks').add({
        'user_id': user_id, 'file_id': context.user_data['file_id'],
        'movieName': context.user_data['name'], 'split_minute': int(context.user_data['len']),
        'watermark': wm, 'lang': lang, 'status': 'pending', 'createdAt': firestore.SERVER_TIMESTAMP
    })
    msg = update.message if update.message else update.callback_query.message
    await msg.reply_text(TEXTS[lang]['done'])
    return ConversationHandler.END

if __name__ == '__main__':
    app = Application.builder().token(os.environ.get('TELEGRAM_TOKEN')).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(set_language, pattern='^setlang_'))
    app.add_handler(CallbackQueryHandler(buy_premium, pattern='buy'))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.VIDEO, start_upload)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name), CallbackQueryHandler(get_name, pattern='skip')],
            LENGTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_length), CallbackQueryHandler(get_length, pattern='skip')],
            WATERMARK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_wm), CallbackQueryHandler(get_wm, pattern='skip')],
        }, fallbacks=[]
    ))
    app.run_polling()
