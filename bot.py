import os, base64, subprocess, asyncio, firebase_admin, json, re
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# Firebase Init
if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if cred_json:
        firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def run_bot():
    # Environment Variables မှ ဆွဲယူခြင်း
    session_str = os.environ.get("SESSION_STRING")
    api_id = os.environ.get("API_ID")
    api_hash = os.environ.get("API_HASH")
    
    if not all([session_str, api_id, api_hash]):
        print("Error: API Credentials Missing!")
        return

    client = TelegramClient(StringSession(session_str), int(api_id), api_hash)
    
    print("Connecting Bot...")
    await client.start()
    print("Bot is Online!")

    while True:
        try:
            # Firestore မှ Pending Task များကို ရှာဖွေခြင်း
            tasks = db.collection('tasks').where(
                filter=FieldFilter("status", "in", ["pending", "processing"])
            ).limit(1).get()
            
            if not tasks:
                await asyncio.sleep(10)
                continue
            
            doc = tasks[0]; data = doc.to_dict(); ref = doc.reference
            uid = int(data['user_id']); v_url = data['value'].strip()
            
            ref.update({'status': 'processing'})

            # Download Logic
            downloaded = False
            if "t.me/" in v_url:
                # Telegram Link ဖြစ်လျှင်
                parts = v_url.split('/')
                msg_id = int(parts[-1])
                peer = parts[-2]
                msg = await client.get_messages(peer, ids=msg_id)
                if msg and msg.media:
                    await client.download_media(msg, "vid.mp4")
                    downloaded = True
            else:
                # yt-dlp ဖြင့် Down ရန်
                try:
                    subprocess.run(['yt-dlp', '--no-check-certificate', '--location', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)
                    if os.path.exists("vid.mp4"): downloaded = True
                except: pass

            if not downloaded: raise Exception("Download Failed")

            # FFmpeg Processing
            duration_sec = sum(int(x) * 60**i for i, x in enumerate(reversed(data.get('len', '5:00').split(':'))))
            filters = []
            if data.get('wm'):
                logic = "x='if(lt(mod(t,10),5),w*0.1,w*0.7)':y='if(lt(mod(t,6),3),h*0.1,h*0.8)'"
                filters.append(f"drawtext=text='{data['wm']}':{logic}:fontcolor=white@0.5:fontsize=30")
            
            # Logo processing
            v_input = ['-i', 'vid.mp4']
            if data.get('logo_data'):
                with open("logo.png", "wb") as f: f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                v_input = ['-i', 'vid.mp4', '-i', 'logo.png']
                pos_map = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}
                filters.append(f"[0:v][1:v]overlay={pos_map[data['pos']]}")

            os.makedirs("parts", exist_ok=True)
            for f in os.listdir("parts"): os.remove(os.path.join("parts", f))

            cmd = ['ffmpeg', '-y'] + v_input + ['-vf', ",".join(filters) if filters else "copy", '-f', 'segment', '-segment_time', str(duration_sec), '-reset_timestamps', '1', 'parts/p_%03d.mp4']
            subprocess.run(cmd, check=True)

            # Uploading
            parts = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            for idx, p in enumerate(parts):
                caption = f"🎬 {data.get('name', 'movie')} - Part {idx+1}"
                await client.send_file(uid, f"parts/{p}", caption=caption)
                ref.update({'last_sent_index': idx})

            ref.delete()
            for f in ["vid.mp4", "logo.png"]: 
                if os.path.exists(f): os.remove(f)

        except Exception as e:
            print(f"Error: {e}")
            try: ref.update({'status': 'pending'})
            except: pass
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_bot())
