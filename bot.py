import os, base64, subprocess, asyncio, firebase_admin, json, re
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession

if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def worker():
    client = TelegramClient(StringSession(os.environ.get("SESSION_STRING")), 36969505, "f129bfcfe08725b285d2a1938fc18380")
    await client.connect()
    
    while True:
        tasks = db.collection('tasks').where("status", "in", ["pending", "processing"]).limit(1).get()
        if not tasks: await asyncio.sleep(15); continue
        
        doc = tasks[0]; data = doc.to_dict(); ref = doc.reference
        uid = int(data['user_id']); lang = data.get('lang', 'my')
        
        try:
            ref.update({'status': 'processing'})
            m_name = data.get('name', 'movie')
            wm_text = data.get('wm', '')
            duration_sec = sum(int(x) * 60**i for i, x in enumerate(reversed(data.get('len', '5:00').split(':'))))

            subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]', '-o', 'vid.mp4', data['value']], check=True)

            moving_logic = "x='if(lt(mod(t,10),5),w*0.1,w*0.7)':y='if(lt(mod(t,6),3),h*0.1,h*0.8)'"
            filters = []
            if wm_text: filters.append(f"drawtext=text='{wm_text}':{moving_logic}:fontcolor=white@0.5:fontsize=30")
            if data.get('logo_data'):
                pos_map = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}
                with open("logo.png", "wb") as f: f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                filters.append(f"movie=logo.png[logo];[v][logo]overlay={pos_map[data['pos']]}")

            os.makedirs("parts", exist_ok=True)
            subprocess.run(['ffmpeg', '-y', '-i', 'vid.mp4', '-vf', ",".join(filters) if filters else "copy", 
                            '-f', 'segment', '-segment_time', str(duration_sec), '-reset_timestamps', '1', 'parts/p_%d.mp4'], check=True)
            
            parts = sorted([f for f in os.listdir("parts")])
            for idx, p in enumerate(parts):
                caption = f"🎬 {m_name} - Part {idx+1}"
                if idx + 1 == len(parts):
                    caption += " (ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else " (End Part) ✅"
                await client.send_file(uid, f"parts/{p}", caption=caption)
                ref.update({'last_sent_index': idx})

            ref.delete()
        except: ref.update({'status': 'pending'})

asyncio.run(worker())
