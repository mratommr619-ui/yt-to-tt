import os, json, asyncio, subprocess, firebase_admin, time, re, base64
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession

if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

TEXTS = {
    'en': {'send': "📤 Part {num}...", 'end': " (End Part) ✅"},
    'my': {'send': "📤 အပိုင်း {num} ပို့နေပါတယ်...", 'end': " (ဇာတ်သိမ်းပိုင်း) ✅"}
}

def parse_duration(val):
    try:
        if ':' in str(val):
            m, s = map(float, str(val).split(':'))
            return int(m * 60 + s)
        return int(float(val) * 60)
    except: return 300

async def worker():
    client = TelegramClient(StringSession(os.environ.get("SESSION_STRING")), int(os.environ.get("API_ID")), os.environ.get("API_HASH"))
    await client.connect()
    
    async with client:
        print("🚀 Worker Engine Started...")
        while True:
            tasks = db.collection('tasks').where("status", "in", ["pending", "processing"])\
                      .order_by("isPremium", direction=firestore.Query.DESCENDING)\
                      .order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()
            
            if not tasks: await asyncio.sleep(15); continue
            
            doc = tasks[0]; data = doc.to_dict(); task_ref = doc.reference
            uid = int(data['user_id'])
            t = TEXTS.get(data.get('lang', 'my'), TEXTS['my'])
            
            try:
                task_ref.update({'status': 'processing'})
                file = "vid.mp4"
                subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '-o', file, data['value']], check=True)

                dur = parse_duration(data.get('len', '5:00'))
                os.makedirs("parts", exist_ok=True)
                subprocess.run(['ffmpeg', '-y', '-i', file, '-f', 'segment', '-segment_time', str(dur), '-reset_timestamps', '1', 'parts/p_%d.mp4'], check=True)

                logo_file = "logo.png"
                has_logo = False
                if data.get('logo_data'):
                    header, encoded = data['logo_data'].split(",", 1)
                    with open(logo_file, "wb") as f: f.write(base64.b64decode(encoded))
                    has_logo = True

                all_parts = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")], key=lambda x: int(re.search(r'\d+', x).group()))
                total = len(all_parts)

                for idx, p in enumerate(all_parts):
                    num = idx + 1
                    if num <= data.get('last_sent_index', -1): continue # Resume logic
                    
                    out = f"f_{num}.mp4"
                    filters = []
                    if has_logo:
                        pos = {"tr": "W-w-10:10", "tl": "10:10", "br": "W-w-10:H-h-10", "bl": "10:H-h-10"}[data['pos']]
                        filters.append(f"movie={logo_file},format=rgba,colorchannelmixer=aa={data['vis']} [l]; [in][l] overlay={pos}")
                    if data.get('wm'):
                        filters.append(f"drawtext=text='{data['wm']}':fontcolor=white@0.4:fontsize=h/20:x='mod(t*100,w)':y='h-th-10'")

                    vf = ",".join(filters)
                    cmd = ['ffmpeg', '-y', '-i', f"parts/{p}"]
                    if vf: cmd += ['-vf', vf, '-c:v', 'libx264', '-crf', '23', out]
                    else: cmd += ['-c', 'copy', out]
                    
                    subprocess.run(cmd, check=True)
                    caption = f"{data.get('name')} {t['send'].format(num=num)}"
                    if num == total: caption += t['end']
                    
                    await client.send_file(uid, out, caption=caption, supports_streaming=True)
                    task_ref.update({'last_sent_index': num})
                    os.remove(out)

                task_ref.delete()
                for f in os.listdir("parts"): os.remove(f"parts/{f}")
            except: task_ref.update({'status': 'pending'}); await asyncio.sleep(10)

if __name__ == "__main__": asyncio.run(worker())
