import os, base64, subprocess, asyncio, firebase_admin, json, re
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# 1. Firebase Configuration
if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if cred_json:
        firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def run_bot():
    # 2. Security Setup
    api_id = int(os.environ.get("API_ID"))
    api_hash = os.environ.get("API_HASH")
    session_str = os.environ.get("SESSION_STRING")
    
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.start()
    print("Bot is online and waiting for tasks...")

    while True:
        try:
            # 3. Task Listening (Pending tasks only)
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).limit(1).get()
            
            if not tasks:
                await asyncio.sleep(5)
                continue
            
            doc = tasks[0]; data = doc.to_dict(); ref = doc.reference
            uid = int(data['user_id']); lang = data.get('lang', 'my')
            v_url = data['value'].strip()
            
            # 4. Instant Feedback to User
            ack_msg = "သင့် video ကို လက်ခံရရှိပါသည်၊ ဖြတ်ပြီးပါက ပြန်လည်ပို့ဆောင်ပေးပါမည်။" if lang == 'my' else "Video received. Will send back once split is done."
            await client.send_message(uid, ack_msg)
            
            ref.update({'status': 'processing'})

            # 5. Smart Download Logic
            if "t.me/" in v_url:
                parts = v_url.split('/')
                msg_obj = await client.get_messages(parts[-2], ids=int(parts[-1]))
                await client.download_media(msg_obj, "vid.mp4")
            else:
                subprocess.run(['yt-dlp', '--no-check-certificate', '--location', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            if not os.path.exists("vid.mp4"): raise Exception("Download Failed")

            # 6. Video Processing with Myanmar Font Support
            duration_sec = sum(int(x) * 60**i for i, x in enumerate(reversed(data.get('len', '5:00').split(':'))))
            filters = []
            
            if data.get('wm'):
                # Pyidaungsu font path ကို သေချာထည့်ပေးရပါမယ်
                wm_text = data['wm']
                logic = "x='if(lt(mod(t,10),5),w*0.1,w*0.7)':y='if(lt(mod(t,6),3),h*0.1,h*0.8)'"
                # Font path သည် server ပေါ်ရှိ နေရာအတိအကျ ဖြစ်ရမည်
                filters.append(f"drawtext=text='{wm_text}':{logic}:fontfile='Pyidaungsu.ttf':fontcolor=white@0.5:fontsize=30")
            
            v_input = ['-i', 'vid.mp4']
            if data.get('logo_data'):
                with open("logo.png", "wb") as f: 
                    f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                v_input = ['-i', 'vid.mp4', '-i', 'logo.png']
                pos_map = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}
                filters.append(f"[0:v][1:v]overlay={pos_map[data['pos']]}")

            os.makedirs("parts", exist_ok=True)
            for f in os.listdir("parts"): os.remove(os.path.join("parts", f))

            cmd = ['ffmpeg', '-y'] + v_input + [
                '-vf', ",".join(filters) if filters else "copy", 
                '-f', 'segment', '-segment_time', str(duration_sec), 
                '-reset_timestamps', '1', 'parts/p_%03d.mp4'
            ]
            subprocess.run(cmd, check=True)

            # 7. Sending Results back to User
            parts = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")], key=lambda x: int(re.findall(r'\d+', x)[0]))
            for idx, p in enumerate(parts):
                caption = f"🎬 {data.get('name')} - Part {idx+1}"
                if idx + 1 == len(parts):
                    caption += " (ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else " (End Part) ✅"
                await client.send_file(uid, f"parts/{p}", caption=caption)
                ref.update({'last_sent_index': idx})

            # Cleanup
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
