import os, base64, subprocess, asyncio, firebase_admin, json, shutil, time, urllib.parse
from firebase_admin import credentials, firestore
from telethon import TelegramClient, events, types
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# --- [ Firebase & Config ] ---
if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if cred_json: firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
WEB_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app/")
# Mini App Link (ဥပမာ - https://t.me/YourBotName/AppName)
MINI_APP_LINK = "https://t.me/yttott_bot/app" 

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

TEXTS = {
    'my': {
        'intro': "🎬 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**\n\nForward ဗီဒီယို သို့မဟုတ် Link များ ပို့ပေးနိုင်ပါသည်။",
        'ack': "ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။ အစီအစဉ်အတိုင်း ပြန်လည်ပို့ဆောင်ပေးပါမည်။",
        'menu': ["🚀 Mini App ဖွင့်ရန်", "👤 My Profile", "💎 Premium ဝယ်ရန်"],
        'part_label': "အပိုင်း",
        'end_tag': " (ဇာတ်သိမ်းပိုင်း) ✅",
        'forward_msg': "✅ ဗီဒီယိုကို မှတ်မိပါသည်။ Mini App တွင် အသေးစိတ်ဖြည့်ရန် အောက်ပါခလုတ်ကို နှိပ်ပါ။"
    },
    'en': {
        'intro': "🎬 **Welcome to Movie Spliter Bot**\n\nPlease send forwarded videos or links.",
        'ack': "Video received! Please wait. Your split videos will be sent in order.",
        'menu': ["🚀 Open Mini App", "👤 My Profile", "💎 Buy Premium"],
        'part_label': "Part",
        'end_tag': " (End Part) ✅",
        'forward_msg': "✅ Video recognized! Click the button below to fill details in Mini App."
    }
}

def get_menu(lang):
    l = lang if lang in TEXTS else 'my'
    buttons = [[types.KeyboardButtonWebApp(text=TEXTS[l]['menu'][0], url=WEB_URL)],
               [types.KeyboardButton(text=TEXTS[l]['menu'][1]), types.KeyboardButton(text=TEXTS[l]['menu'][2])]]
    return types.ReplyKeyboardMarkup(rows=[types.KeyboardRow(b) for b in buttons], resize=True, persistent=True)

# --- [ 1. Start & Forward Link Handler ] ---
@client.on(events.NewMessage)
async def handle_messages(event):
    uid = str(event.sender_id)
    user_ref = db.collection('users').document(uid)
    u_doc = user_ref.get()
    lang = u_doc.to_dict().get('lang', 'my') if u_doc.exists else 'my'

    if event.text == '/start':
        if not u_doc.exists:
            user_ref.set({'uid': uid, 'lang': 'my', 'is_premium': False, 'expiry_date': 'N/A', 'createdAt': firestore.SERVER_TIMESTAMP})
        await event.respond(TEXTS[lang]['intro'], buttons=get_menu(lang))
        return

    # Forward ဗီဒီယို သို့မဟုတ် Link ကို စစ်ဆေးခြင်း
    video_url = ""
    if event.message.video:
        # Public Channel ဆိုလျှင် Link ယူသည်၊ မဟုတ်လျှင် Bot ဆီ တိုက်ရိုက်ပို့ခိုင်းသည်
        if event.is_channel:
            video_url = f"https://t.me/{event.chat.username}/{event.message.id}" if event.chat.username else f"https://t.me/c/{event.chat_id}/{event.message.id}"
    elif event.text and ("http" in event.text or "t.me/" in event.text):
        video_url = event.text.strip()

    if video_url:
        encoded_url = urllib.parse.quote(video_url)
        # Parameter ကို startapp အနေနဲ့ ပို့သည်
        app_link = f"{MINI_APP_LINK}?startapp={encoded_url}"
        btn = [[types.KeyboardButtonWebApp(text=TEXTS[lang]['menu'][0], url=app_link)]]
        await event.respond(TEXTS[lang]['forward_msg'], buttons=types.ReplyKeyboardMarkup(rows=[types.KeyboardRow(b) for b in btn], resize=True))

# --- [ 2. Background Ack Handler ] ---
async def ack_handler():
    while True:
        try:
            pendings = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).get()
            for p in pendings:
                data = p.to_dict()
                uid, lang = int(data.get('user_id', 0)), data.get('lang', 'my')
                await client.send_message(uid, TEXTS[lang]['ack'], buttons=get_menu(lang))
                p.reference.update({'status': 'queued'})
            await asyncio.sleep(3)
        except: await asyncio.sleep(5)

# --- [ 3. Main Splitter Engine ] ---
async def worker_engine():
    while True:
        try:
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "processing")).limit(1).get()
            if not tasks:
                tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "queued")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()

            if not tasks: await asyncio.sleep(5); continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            uid, lang, v_url = int(data.get('user_id', 0)), data.get('lang', 'my'), data.get('value', '').strip()
            if data['status'] == 'queued': ref.update({'status': 'processing'})

            # Download Logic (Telegram + Web Links)
            if not os.path.exists("vid.mp4"):
                if "t.me/" in v_url:
                    try:
                        p = v_url.split('/')
                        channel = int(f"-100{p[-2]}") if p[-2].isdigit() else p[-2]
                        msg = await client.get_messages(channel, ids=int(p[-1]))
                        await client.download_media(msg, "vid.mp4")
                    except: pass
                
                if not os.path.exists("vid.mp4"):
                    subprocess.run(['yt-dlp', '--no-check-certificate', '--follow-redirects', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            # FFmpeg Splitting (Logo 60% Alpha + Watermark)
            os.makedirs("parts", exist_ok=True)
            if not os.listdir("parts"):
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

            # Smart Delivery (Multi-lang Caption & End Tag)
            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            ls_idx, movie_name, total_parts = data.get('last_sent_index', -1), data.get('name') or "Movie Name", len(files)
            
            for idx, p in enumerate(files):
                if idx > ls_idx:
                    curr = idx + 1
                    caption = f"🎬 {movie_name} - {TEXTS[lang]['part_label']} ({curr})"
                    if curr == total_parts: caption += TEXTS[lang]['end_tag']
                    await client.send_file(uid, f"parts/{p}", caption=caption, buttons=get_menu(lang))
                    ref.update({'last_sent_index': idx})

            ref.delete(); shutil.rmtree("parts")
            if os.path.exists("vid.mp4"): os.remove("vid.mp4")
            if os.path.exists("logo.png"): os.remove("logo.png")

        except Exception as e:
            print(f"🚨 Error: {e}"); await asyncio.sleep(10)

# --- [ Execution ] ---
async def main():
    await client.start()
    await asyncio.gather(ack_handler(), worker_engine(), client.run_until_disconnected())

if __name__ == "__main__":
    asyncio.run(main())
