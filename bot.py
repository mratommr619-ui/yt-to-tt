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

ERR_MSG = {'my': "⚠️ ဗီဒီယို ဒေါင်းလုဒ်ဆွဲရာတွင် အမှားရှိနေပါသည်။", 'en': "⚠️ Download Error."}
LABEL = {'my': {'part': "အပိုင်း", 'end': " (ဇာတ်သိမ်းပိုင်း) ✅"}, 'en': {'part': "Part", 'end': " (End Part) ✅"}}

async def worker_engine():
    while True:
        try:
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "queued")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()
            if not tasks: await asyncio.sleep(10); continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            uid, v_url = int(data.get('user_id', 0)), data.get('value', '').strip()
            ref.update({'status': 'processing'})

            u_doc = db.collection('users').document(str(uid)).get().to_dict() or {}
            is_premium = u_doc.get('is_premium', False)

            success = False
            if "t.me/" in v_url:
                try:
                    msg = await client.get_messages(uid, ids=int(v_url.split('/')[-1]))
                    await client.download_media(msg, "vid.mp4"); success = True
                except: success = False
            else:
                try:
                    res = subprocess.run(['yt-dlp', '--no-check-certificate', '--user-agent', 'Mozilla/5.0', '-S', 'ext:mp4:m4a', '--follow-redirects', '-o', 'vid.mp4', v_url], timeout=400)
                    success = (res.returncode == 0)
                except: success = False

            if not success or not os.path.exists("vid.mp4"):
                await client.send_message(uid, ERR_MSG.get(data.get('lang', 'my'))); ref.delete(); continue

            # --- [ Phase 2: Professional FFmpeg Logic ] ---
            os.makedirs("parts", exist_ok=True)
            dur = sum(x * 60**i for i, x in enumerate(map(int, reversed((data.get('len') or "5:00").split(':')))))
            
            # ✅ User Watermark: Screen တစ်ပြင်လုံး Wave လှိုင်းလိုဝဲနေအောင် (Opacity 50%, Size 75)
            u_wm = data.get('wm', '')
            user_filter = (
                f"drawtext=text='{u_wm}':x='(w-text_w)/2+((w-text_w)/3)*sin(t/3)':"
                f"y='(h-text_h)/2+((h-text_h)/3)*cos(t/2)':"
                f"fontfile='Pyidaungsu.ttf':fontcolor=white@0.5:fontsize=75"
            ) if u_wm else "null"
            
            # ✅ Free Bot Watermark: Bottom Center (Opacity 50%, Size 45)
            bot_filter = ""
            if not is_premium:
                bot_filter = ",drawtext=text='https://t.me/tt_uploader_bot':x=(w-text_w)/2:y=h-text_h-30:fontfile='Pyidaungsu.ttf':fontcolor=white@0.5:fontsize=45"

            final_vf = f"{user_filter}{bot_filter}"
            v_in = ['-i', 'vid.mp4']
            
            if data.get('logo_data'):
                with open("logo.png", "wb") as f: f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                v_in += ['-i', 'logo.png']
                pos = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}.get(data.get('pos', 'tr'), "W-w-15:15")
                f_c = f"[1:v]scale=150:-1,format=rgba,colorchannelmixer=aa=0.6[l];[0:v]{final_vf}[v1];[v1][l]overlay={pos}"
                subprocess.run(['ffmpeg', '-y'] + v_in + ['-filter_complex', f_c, '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy', '-f', 'segment', '-segment_time', str(dur), '-reset_timestamps', '1', 'parts/p_%03d.mp4'], check=True)
            else:
                subprocess.run(['ffmpeg', '-y'] + v_in + ['-vf', final_vf, '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy', '-f', 'segment', '-segment_time', str(dur), '-reset_timestamps', '1', 'parts/p_%03d.mp4'], check=True)

            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            for idx, p in enumerate(files):
                cap = f"🎬 {data.get('name','Movie')} - {LABEL[data.get('lang','my')]['part']} ({idx+1})"
                if idx+1 == len(files): cap += LABEL[data.get('lang','my')]['end']
                await client.send_file(uid, f"parts/{p}", caption=cap)
            ref.delete()
        except Exception as e:
            if doc: ref.delete()
            await asyncio.sleep(5)
        finally:
            if os.path.exists("parts"): shutil.rmtree("parts")
            for f in ["vid.mp4", "logo.png"]: 
                if os.path.exists(f): os.remove(f)

async def main():
    await client.start()
    await worker_engine()

if __name__ == "__main__":
    asyncio.run(main())
