import os, base64, subprocess, asyncio, firebase_admin, json, shutil, time, urllib.parse
from datetime import datetime
from firebase_admin import credentials, firestore
from telethon import TelegramClient, events, types, Button
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# --- [ Configuration ] ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
WEB_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app/")

KPAY, AYAPAY, BEP20 = "09695616591", "09695616591", "0x56824c51be35937da7E60a6223E82cD1795984cC"

if not firebase_admin._apps:
    cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
    if cred_json: firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# --- [ Texts from your app.py ] ---
TEXTS = {
    'my': {
        'intro': "🎬 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'open': "🚀 Mini App ဖွင့်ရန်",
        'profile': "👤 My Profile",
        'buy': "💎 Premium ဝယ်ရန်",
        'payment': "💎 **Premium Upgrade**\n\n💰 **၁ လ:** 3000 ကျပ် / 1.0 USDT\n💳 **KPay:** `{kpay}`\n💳 **AYAPay:** `{ayapay}`\n🌐 **BEP20:** `{bep20}`\n⚠️ **Note:** ID `{uid}` ကို Screenshot နှင့်အတူ ပို့ပေးပါ။",
        'forward_msg': "✅ ဗီဒီယိုကို မှတ်မိပါသည်။ Mini App တွင် အသေးစိတ်ဖြည့်ရန် အောက်ပါခလုတ်ကို နှိပ်ပါ။",
        'ack': "ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။",
        'part_label': "အပိုင်း",
        'end_tag': " (ဇာတ်သိမ်းပိုင်း) ✅"
    },
    'en': {
        'intro': "🎬 **Welcome to Movie Spliter Bot**",
        'open': "🚀 Open Mini App",
        'profile': "👤 My Profile",
        'buy': "💎 Buy Premium",
        'payment': "💎 **Premium Upgrade**\n\n💰 **1 Month:** 3000 MMK / 1.0 USDT\n💳 **KPay:** `{kpay}`\n💳 **AYAPay:** `{ayapay}`\n🌐 **BEP20:** `{bep20}`\n⚠️ **Note:** Send ID `{uid}` with screenshot.",
        'forward_msg': "✅ Video recognized! Click the button below to open Mini App.",
        'ack': "Video received! Please wait.",
        'part_label': "Part",
        'end_tag': " (End Part) ✅"
    }
}

# Keyboard Builder (Mix Error လုံးဝမတက်အောင် types သုံးပြီး စနစ်တကျ ဆောက်ထားသည်)
def get_main_kb(lang, webapp_url):
    return types.ReplyKeyboardMarkup(rows=[
        types.KeyboardRow([types.KeyboardButtonWebApp(text=TEXTS[lang]['open'], url=webapp_url)]),
        types.KeyboardRow([types.KeyboardButton(text=TEXTS[lang]['profile']), types.KeyboardButton(text=TEXTS[lang]['buy'])])
    ], resize=True, persistent=True)

# --- [ 1. Message Handler ] ---
@client.on(events.NewMessage)
async def handle_messages(event):
    uid = str(event.sender_id)
    user_ref = db.collection('users').document(uid)
    u_doc = user_ref.get().to_dict() or {}
    lang = u_doc.get('lang', 'my')

    # Start Command (Language Selection)
    if event.text == '/start':
        btns = [[Button.inline("🇲🇲 မြန်မာစာ", b"lang_my"), Button.inline("🇺🇸 English", b"lang_en")]]
        await event.respond("Choose Language / ဘာသာစကားရွေးချယ်ပါ -", buttons=btns)
        return

    # Profile Display (Matching app.py logic)
    if event.text in [TEXTS['my']['profile'], TEXTS['en']['profile']]:
        is_premium = u_doc.get('is_premium', False)
        exp_str = u_doc.get('expiry_date', 'N/A')
        status = "Premium Member ✅" if is_premium else "Free Member ❌"
        msg = f"👤 **User Profile**\n\n🆔 ID: `{uid}`\n👑 Status: **{status}**\n📅 Expiry: `{exp_str}`"
        await event.respond(msg, buttons=get_main_kb(lang, WEB_URL))
        return

    # Premium Buy (Matching app.py logic)
    if event.text in [TEXTS['my']['buy'], TEXTS['en']['buy']]:
        msg = TEXTS[lang]['payment'].format(uid=uid, kpay=KPAY, ayapay=AYAPAY, bep20=BEP20)
        await event.respond(msg, buttons=get_main_kb(lang, WEB_URL))
        return

    # Forward Video Logic (The Auto-fill Part)
    if event.message.video or event.message.document:
        video_link = f"https://t.me/me/{event.message.id}"
        encoded_link = urllib.parse.quote(video_link)
        dynamic_url = f"{WEB_URL}?link={encoded_link}"
        await event.respond(TEXTS[lang]['forward_msg'], buttons=get_main_kb(lang, dynamic_url))

# --- [ 2. Language Callback ] ---
@client.on(events.CallbackQuery(pattern=b"lang_"))
async def set_lang(event):
    lang = event.data.decode().split("_")[1]
    uid = str(event.sender_id)
    db.collection('users').document(uid).set({'lang': lang, 'uid': uid, 'is_premium': False, 'expiry_date': 'N/A'}, merge=True)
    await event.delete()
    await client.send_message(uid, TEXTS[lang]['intro'], buttons=get_main_kb(lang, WEB_URL))

# --- [ 3. Background Ack Handler ] ---
async def ack_handler():
    while True:
        try:
            pendings = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).get()
            for p in pendings:
                data = p.to_dict()
                uid, lang = int(data.get('user_id', 0)), data.get('lang', 'my')
                await client.send_message(uid, TEXTS[lang]['ack'], buttons=get_main_kb(lang, WEB_URL))
                p.reference.update({'status': 'queued'})
            await asyncio.sleep(5)
        except: await asyncio.sleep(10)

# --- [ 4. Worker Engine (Processing) ] ---
async def worker_engine():
    while True:
        try:
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "processing")).limit(1).get()
            if not tasks:
                tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "queued")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()

            if not tasks: await asyncio.sleep(10); continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            uid, lang, v_url = int(data.get('user_id', 0)), data.get('lang', 'my'), data.get('value', '').strip()
            if data['status'] == 'queued': ref.update({'status': 'processing'})

            if not os.path.exists("vid.mp4"):
                if "t.me/" in v_url:
                    msg_id = int(v_url.split('/')[-1])
                    msg = await client.get_messages(uid, ids=msg_id)
                    await client.download_media(msg, "vid.mp4")
                else:
                    subprocess.run(['yt-dlp', '--no-check-certificate', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            os.makedirs("parts", exist_ok=True)
            if not os.listdir("parts") and os.path.exists("vid.mp4"):
                dur = sum(x * 60**i for i, x in enumerate(map(int, reversed((data.get('len') or "5:00").split(':')))))
                wm = data.get('wm', '')
                drawtext = f"drawtext=text='{wm}':x='(w-text_w)/2+(w-text_w)/2*sin(t/2)':y='(h-text_h)/2+(h-text_h)/2*sin(t/3)':fontfile='Pyidaungsu.ttf':fontcolor=white@0.4:fontsize=50" if wm else "null"
                
                v_in = ['-i', 'vid.mp4']
                if data.get('logo_data'):
                    with open("logo.png", "wb") as f: f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                    v_in += ['-i', 'logo.png']
                    pos = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}.get(data.get('pos', 'tr'), "W-w-15:15")
                    f_c = f"[1:v]scale=150:-1,format=rgba,colorchannelmixer=aa=0.6[l];[0:v]{drawtext}[v1];[v1][l]overlay={pos}"
                    subprocess.run(['ffmpeg', '-y'] + v_in + ['-filter_complex', f_c, '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy', '-f', 'segment', '-segment_time', str(dur), '-reset_timestamps', '1', 'parts/p_%03d.mp4'], check=True)
                else:
                    subprocess.run(['ffmpeg', '-y'] + v_in + ['-vf', drawtext, '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy', '-f', 'segment', '-segment_time', str(dur), '-reset_timestamps', '1', 'parts/p_%03d.mp4'], check=True)

            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            total_parts = len(files)
            for idx, p in enumerate(files):
                curr = idx + 1
                caption = f"🎬 {data.get('name', 'Movie')} - {TEXTS[lang]['part_label']} ({curr})"
                if curr == total_parts: caption += TEXTS[lang]['end_tag']
                await client.send_file(uid, f"parts/{p}", caption=caption, buttons=get_main_kb(lang, WEB_URL))

            ref.delete(); shutil.rmtree("parts")
            if os.path.exists("vid.mp4"): os.remove("vid.mp4")
            if os.path.exists("logo.png"): os.remove("logo.png")

        except Exception as e: print(f"Error: {e}"); await asyncio.sleep(10)

async def main():
    await client.start()
    await asyncio.gather(ack_handler(), worker_engine(), client.run_until_disconnected())

if __name__ == "__main__":
    asyncio.run(main())
