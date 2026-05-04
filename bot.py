import os, base64, subprocess, asyncio, firebase_admin, json, shutil, time, urllib.parse
from firebase_admin import credentials, firestore
from telethon import TelegramClient, events, Button
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

# BotFather Screenshot အရ အကိုက်ညီဆုံး Link
BOT_USERNAME = "tt_uploader_bot"  
APP_SHORT_NAME = "myapp"         
MINI_APP_LINK = f"https://t.me/{BOT_USERNAME}/{APP_SHORT_NAME}"

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# Language Dictionary (Firebase lang နဲ့ ညှိထားသည်)
TEXTS = {
    'my': {
        'intro': "🎬 **Movie Spliter Bot မှ ကြိုဆိုပါတယ်**",
        'ack': "ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။",
        'part_label': "အပိုင်း",
        'end_tag': " (ဇာတ်သိမ်းပိုင်း) ✅",
        'forward_msg': "✅ ဗီဒီယိုကို မှတ်မိပါသည်။ Mini App တွင် အသေးစိတ်ဖြည့်ရန် အောက်ပါခလုတ်ကို နှိပ်ပါ။",
        'menu_open': "🚀 Mini App ဖွင့်ရန်"
    },
    'en': {
        'intro': "🎬 **Welcome to Movie Spliter Bot**",
        'ack': "Video received! Please wait.",
        'part_label': "Part",
        'end_tag': " (End Part) ✅",
        'forward_msg': "✅ Video recognized! Click the button below to fill details in Mini App.",
        'menu_open': "🚀 Open Mini App"
    }
}

# --- [ 1. Handle Messages & Forward ] ---
@client.on(events.NewMessage)
async def handle_messages(event):
    uid = str(event.sender_id)
    user_ref = db.collection('users').document(uid)
    u_doc = user_ref.get()
    
    # App.py မှာ ရွေးထားတဲ့ language ကို ယူသုံးခြင်း
    lang = u_doc.to_dict().get('lang', 'my') if u_doc.exists else 'my'

    if event.text == '/start':
        await event.respond(
            TEXTS[lang]['intro'], 
            buttons=[
                [Button.url(TEXTS[lang]['menu_open'], MINI_APP_LINK)],
                [Button.text("👤 My Profile"), Button.text("💎 Buy Premium")]
            ]
        )
        return

    # Forward Logic: Video Link parameter ဆောက်သည်
    if event.message.video or event.message.document:
        msg_id = event.message.id
        video_url = f"https://t.me/me/{msg_id}" 
        encoded_url = urllib.parse.quote(video_url)
        app_link = f"{MINI_APP_LINK}?startapp={encoded_url}"
        await event.respond(TEXTS[lang]['forward_msg'], buttons=[[Button.url(TEXTS[lang]['menu_open'], app_link)]])

# --- [ 2. Background Ack Handler ] ---
async def ack_handler():
    while True:
        try:
            pendings = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).get()
            for p in pendings:
                data = p.to_dict()
                uid, lang = int(data.get('user_id', 0)), data.get('lang', 'my')
                await client.send_message(uid, TEXTS[lang]['ack'])
                p.reference.update({'status': 'queued'})
            await asyncio.sleep(5)
        except: await asyncio.sleep(10)

# --- [ 3. Worker Engine (All Original Functions Restored) ] ---
async def worker_engine():
    while True:
        try:
            # Processing ဖြစ်နေတာရှိရင် resume လုပ်မယ်
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "processing")).limit(1).get()
            if not tasks:
                tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "queued")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()

            if not tasks: await asyncio.sleep(10); continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            uid, lang, v_url = int(data.get('user_id', 0)), data.get('lang', 'my'), data.get('value', '').strip()
            if data['status'] == 'queued': ref.update({'status': 'processing'})

            # Download
            if not os.path.exists("vid.mp4"):
                if "t.me/" in v_url:
                    msg_id = int(v_url.split('/')[-1])
                    msg = await client.get_messages(uid, ids=msg_id)
                    await client.download_media(msg, "vid.mp4")
                else: subprocess.run(['yt-dlp', '--no-check-certificate', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            # FFmpeg: Logo 60% Alpha + Watermark
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

            # Delivery: Multi-lang Caption Restored
            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            ls_idx, movie_name, total_parts = data.get('last_sent_index', -1), data.get('name') or "Movie", len(files)
            for idx, p in enumerate(files):
                if idx > ls_idx:
                    curr = idx + 1
                    # ⚠️ ဤနေရာတွင် lang အလိုက် Caption ပြောင်းလဲပါသည်
                    caption = f"🎬 {movie_name} - {TEXTS[lang]['part_label']} ({curr})"
                    if curr == total_parts: caption += TEXTS[lang]['end_tag']
                    await client.send_file(uid, f"parts/{p}", caption=caption)
                    ref.update({'last_sent_index': idx})

            ref.delete(); shutil.rmtree("parts")
            if os.path.exists("vid.mp4"): os.remove("vid.mp4")
            if os.path.exists("logo.png"): os.remove("logo.png")

        except Exception as e: print(f"Error: {e}"); await asyncio.sleep(10)

async def main():
    await client.start()
    await asyncio.gather(ack_handler(), worker_engine(), client.run_until_disconnected())

if __name__ == "__main__":
    asyncio.run(main())
