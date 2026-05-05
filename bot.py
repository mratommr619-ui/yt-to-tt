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

# Error Messages
ERR_MSG = {
    'my': "⚠️ စိတ်မရှိပါနဲ့။ ဗီဒီယို ဒေါင်းလုဒ်ဆွဲရာတွင် အမှားအယွင်းရှိနေပါသည်။ လင့်ခ်အမှန်ဖြစ်မဖြစ် ပြန်စစ်ပေးပါ။",
    'en': "⚠️ Sorry! An error occurred while downloading the video. Please check if the link is correct."
}

LABEL = {
    'my': {'part': "အပိုင်း", 'end': " (ဇာတ်သိမ်းပိုင်း) ✅"},
    'en': {'part': "Part", 'end': " (End Part) ✅"}
}

async def worker_engine():
    while True:
        doc_ref = None
        try:
            # Queued ဖြစ်နေသော Task တစ်ခုကို ယူသည်
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "queued")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()
            
            if not tasks:
                await asyncio.sleep(10); continue
            
            doc = tasks[0]; doc_ref = doc.reference; data = doc.to_dict()
            uid, lang, v_url = int(data.get('user_id', 0)), data.get('lang', 'my'), data.get('value', '').strip()
            movie_name = data.get('name', 'Movie')
            
            doc_ref.update({'status': 'processing'})
            print(f"🛠 Processing: {movie_name} for {uid}")

            # --- [ Phase 1: Download with Browser Mimic & Short URL handling ] ---
            success = False
            if "t.me/" in v_url:
                try:
                    msg_id = int(v_url.split('/')[-1])
                    msg = await client.get_messages(uid, ids=msg_id)
                    if msg and (msg.video or msg.document):
                        await client.download_media(msg, "vid.mp4")
                        success = True
                except: success = False
            else:
                # yt-dlp config: Browser Mimic, Format selection, and Short URL handling
                try:
                    res = subprocess.run([
                        'yt-dlp', 
                        '--no-check-certificate', 
                        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                        '-S', 'ext:mp4:m4a', # Quality ကောင်းသော MP4 ကို ဦးစားပေးသည်
                        '--geo-bypass',      # ဒေသကန့်သတ်ချက်များ ကျော်ရန်
                        '--follow-redirects', # Link အတိုများကို အဆုံးထိ လိုက်ဖတ်ရန်
                        '-o', 'vid.mp4', 
                        v_url
                    ], timeout=400) # Download အတွက် အချိန်ပိုပေးထားသည်
                    if res.returncode == 0: success = True
                except: success = False

            # ဒေါင်းလို့မရလျှင် User ဆီ စာပို့ပြီး Task ဖျက်ကာ ကျော်သွားမည်
            if not success or not os.path.exists("vid.mp4"):
                await client.send_message(uid, ERR_MSG[lang])
                doc_ref.delete()
                print(f"❌ Failed to download {movie_name}. Task deleted.")
                continue

            # --- [ Phase 2: FFmpeg Split ] ---
            os.makedirs("parts", exist_ok=True)
            dur_str = data.get('len') or "5:00"
            dur = sum(x * 60**i for i, x in enumerate(map(int, reversed(dur_str.split(':')))))
            
            wm = data.get('wm', '')
            drawtext = f"drawtext=text='{wm}':x='(w-text_w)/2+(w-text_w)/2*sin(t/2)':y='(h-text_h)/2+(h-text_h)/2*sin(t/3)':fontfile='Pyidaungsu.ttf':fontcolor=white@0.4:fontsize=50" if wm else "null"
            
            v_in = ['-i', 'vid.mp4']
            if data.get('logo_data'):
                with open("logo.png", "wb") as f: 
                    f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                v_in += ['-i', 'logo.png']
                pos = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}.get(data.get('pos', 'tr'), "W-w-15:15")
                f_c = f"[1:v]scale=150:-1,format=rgba,colorchannelmixer=aa=0.6[l];[0:v]{drawtext}[v1];[v1][l]overlay={pos}"
                subprocess.run(['ffmpeg', '-y'] + v_in + ['-filter_complex', f_c, '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy', '-f', 'segment', '-segment_time', str(dur), '-reset_timestamps', '1', 'parts/p_%03d.mp4'], check=True)
            else:
                subprocess.run(['ffmpeg', '-y'] + v_in + ['-vf', drawtext, '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy', '-f', 'segment', '-segment_time', str(dur), '-reset_timestamps', '1', 'parts/p_%03d.mp4'], check=True)

            # --- [ Phase 3: Delivery ] ---
            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            for idx, p in enumerate(files):
                curr = idx + 1
                caption = f"🎬 {movie_name} - {LABEL[lang]['part']} ({curr})"
                if curr == len(files): caption += LABEL[lang]['end']
                await client.send_file(uid, f"parts/{p}", caption=caption)

            # Task အောင်မြင်စွာ ပြီးဆုံးလျှင် ဖျက်သည်
            doc_ref.delete()
            print(f"✅ Success: {movie_name} delivered.")

        except Exception as e:
            print(f"🚨 Critical Error: {e}")
            if doc_ref:
                try:
                    # အမှားတက်လျှင် User ဆီ အသိပေးပြီး task ဖျက်မည်
                    await client.send_message(uid, ERR_MSG[lang])
                    doc_ref.delete()
                except: pass
            await asyncio.sleep(5)
        
        finally:
            # File များ သန့်ရှင်းရေးလုပ်သည်
            if os.path.exists("parts"): shutil.rmtree("parts")
            if os.path.exists("vid.mp4"): os.remove("vid.mp4")
            if os.path.exists("logo.png"): os.remove("logo.png")

async def main():
    await client.start()
    print("🚀 Worker Engine is running with Universal Downloader...")
    await worker_engine()

if __name__ == "__main__":
    asyncio.run(main())
