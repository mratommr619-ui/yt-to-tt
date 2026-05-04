import os, base64, subprocess, asyncio, firebase_admin, json, shutil, time
from firebase_admin import credentials, firestore
from telethon import TelegramClient, types
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# --- [ Configuration ] ---
if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if cred_json: firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

LABEL = {
    'my': {'part': "အပိုင်း", 'end': " (ဇာတ်သိမ်းပိုင်း) ✅"},
    'en': {'part': "Part", 'end': " (End Part) ✅"}
}

async def worker_engine():
    while True:
        try:
            # app.py က queued လို့ ပြောင်းပေးလိုက်သော task ကို ယူသည်
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "queued")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()
            if not tasks:
                await asyncio.sleep(10); continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            uid, lang, v_url = int(data.get('user_id', 0)), data.get('lang', 'my'), data.get('value', '').strip()
            ref.update({'status': 'processing'})

            # Download Logic
            if not os.path.exists("vid.mp4"):
                if "t.me/" in v_url:
                    msg_id = int(v_url.split('/')[-1])
                    msg = await client.get_messages(uid, ids=msg_id)
                    await client.download_media(msg, "vid.mp4")
                else: subprocess.run(['yt-dlp', '--no-check-certificate', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            # FFmpeg: Logo 60% Alpha & Moving Watermark
            os.makedirs("parts", exist_ok=True)
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

            # Delivery
            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            total = len(files)
            for idx, p in enumerate(files):
                curr = idx + 1
                caption = f"🎬 {data.get('name', 'Movie')} - {LABEL[lang]['part']} ({curr})"
                if curr == total: caption += LABEL[lang]['end']
                await client.send_file(uid, f"parts/{p}", caption=caption)

            # Cleanup
            ref.delete(); shutil.rmtree("parts")
            if os.path.exists("vid.mp4"): os.remove("vid.mp4")
            if os.path.exists("logo.png"): os.remove("logo.png")

        except Exception as e: print(f"🚨 Worker Error: {e}"); await asyncio.sleep(10)

async def main():
    await client.start()
    print("🚀 Worker Engine is running...")
    await worker_engine()

if __name__ == "__main__":
    asyncio.run(main())
