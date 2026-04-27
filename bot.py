import os, json, asyncio, subprocess, firebase_admin, time
from firebase_admin import credentials, firestore
from pyrogram import Client

cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def process_video():
    async with Client("worker", int(os.environ.get("API_ID")), os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN")) as app:
        print("🚀 Worker started. Checking tasks...")
        start_time = time.time()
        
        while time.time() - start_time < 300: 
            query = db.collection('tasks').where("status", "==", "pending").order_by("createdAt").limit(1).get()
            if not query:
                await asyncio.sleep(10); continue
            
            doc = query[0]; data = doc.to_dict()
            try: doc.reference.update({'status': 'processing'})
            except: continue

            try:
                target = "movie.mp4"
                if data['type'] == 'video':
                    await app.download_media(data['value'], file_name=target)
                else:
                    cmd = ['yt-dlp', '-f', 'mp4', '--no-check-certificate', '-o', target, data['value']]
                    subprocess.run(cmd, check=True)

                split_s = int(data.get('len', 5)) * 60
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', segment, '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                
                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(x.split('_')[1].split('.')[0]))
                for i, p in enumerate(parts):
                    out = f"final_{i}.mp4"
                    wm = data.get('wm', '')
                    if wm:
                        vf = f"drawtext=text='{wm}':fontcolor=white:fontsize=h/20:x=10:y=10"
                        subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                    else:
                        os.rename(p, out)
                    
                    await app.send_video(data['user_id'], video=out, caption=f"{data.get('name')} Part {i+1}")
                    if os.path.exists(out): os.remove(out)
                    if os.path.exists(p): os.remove(p)

                if os.path.exists(target): os.remove(target)
                doc.reference.update({'status': 'completed'})
            except Exception as e:
                doc.reference.update({'status': 'error', 'error_msg': str(e)})

if __name__ == "__main__":
    asyncio.run(process_video())
