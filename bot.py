import os, base64, subprocess, asyncio, firebase_admin, json, re
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# Firebase Init
if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def worker():
    client = TelegramClient(StringSession(os.environ.get("SESSION_STRING")), 36969505, "f129bfcfe08725b285d2a1938fc18380")
    await client.connect()
    
    while True:
        # Pending Tasks များကို ရှာခြင်း
        tasks = db.collection('tasks').where(filter=FieldFilter("status", "in", ["pending", "processing"])).limit(1).get()
        
        if not tasks: 
            await asyncio.sleep(10)
            continue
        
        doc = tasks[0]; data = doc.to_dict(); ref = doc.reference
        uid = int(data['user_id']); lang = data.get('lang', 'my')
        
        try:
            ref.update({'status': 'processing'})
            m_name = data.get('name', 'movie')
            wm_text = data.get('wm', '')
            v_url = data['value'].strip()
            
            # ၁။ Download Logic (Telegram vs Other Links)
            if "t.me/" in v_url:
                # Telegram Link ဖြစ်လျှင် Telethon ဖြင့် Down ရန်
                parts = v_url.split('/')
                msg_id = int(parts[-1])
                # Channel/Group username သို့မဟုတ် ID ကို ယူခြင်း
                peer = parts[-2]
                msg = await client.get_messages(peer, ids=msg_id)
                if msg and msg.media:
                    await client.download_media(msg, "vid.mp4")
                else:
                    raise Exception("Telegram Media Not Found")
            else:
                # အခြား Link များ (Short URL အပါအဝင်) ကို yt-dlp ဖြင့် Down ရန်
                # --no-check-certificate နှင့် --location တို့က short link များကို ဖြည်ပေးသည်
                subprocess.run([
                    'yt-dlp', 
                    '--no-check-certificate',
                    '--location',
                    '-f', 'b[ext=mp4]/b', 
                    '-o', 'vid.mp4', 
                    v_url
                ], check=True)

            if not os.path.exists("vid.mp4"):
                raise Exception("Download Failed - File not found")

            # ၂။ FFmpeg Video Processing
            duration_sec = sum(int(x) * 60**i for i, x in enumerate(reversed(data.get('len', '5:00').split(':'))))
            filters = []
            
            # Watermark moving logic
            if wm_text:
                moving_logic = "x='if(lt(mod(t,10),5),w*0.1,w*0.7)':y='if(lt(mod(t,6),3),h*0.1,h*0.8)'"
                filters.append(f"drawtext=text='{wm_text}':{moving_logic}:fontcolor=white@0.5:fontsize=30")
            
            v_input = ['-i', 'vid.mp4']
            if data.get('logo_data'):
                pos_map = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}
                with open("logo.png", "wb") as f: 
                    f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                v_input = ['-i', 'vid.mp4', '-i', 'logo.png']
                filters.append(f"[0:v][1:v]overlay={pos_map[data['pos']]}")

            os.makedirs("parts", exist_ok=True)
            for f in os.listdir("parts"): os.remove(os.path.join("parts", f)) # Clear old data

            cmd = ['ffmpeg', '-y'] + v_input + [
                '-vf', ",".join(filters) if filters else "copy", 
                '-f', 'segment', 
                '-segment_time', str(duration_sec), 
                '-reset_timestamps', '1', 
                'parts/p_%d.mp4'
            ]
            subprocess.run(cmd, check=True)
            
            # ၃။ Sending Parts to User
            parts = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")], 
                           key=lambda x: int(re.findall(r'\d+', x)[0]))
            
            for idx, p in enumerate(parts):
                caption = f"🎬 {m_name} - Part {idx+1}"
                if idx + 1 == len(parts):
                    caption += " (ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else " (End Part) ✅"
                
                await client.send_file(uid, f"parts/{p}", caption=caption)
                ref.update({'last_sent_index': idx})

            # Cleanup
            ref.delete()
            if os.path.exists("vid.mp4"): os.remove("vid.mp4")
            if os.path.exists("logo.png"): os.remove("logo.png")

        except Exception as e:
            print(f"Error occurred: {e}")
            ref.update({'status': 'pending'})
            await asyncio.sleep(5)

asyncio.run(worker())
