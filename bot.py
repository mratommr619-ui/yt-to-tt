import os, json, asyncio, subprocess, firebase_admin, gdown, time
from firebase_admin import credentials, firestore
from pyrogram import Client

cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT')))
if not firebase_admin._apps: firebase_admin.initialize_app(cred)
db = firestore.client()

async def process_video():
    async with Client("worker", int(os.environ.get("API_ID")), os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN")) as app:
        print("🚀 Worker started and checking for tasks...")
        
        # GitHub Action တစ်ခါ run ရင် ၅ မိနစ် (၃၀၀ စက္ကန့်) ကြာအောင် Loop ပတ်ပြီး Task ရှာမယ်
        start_time = time.time()
        while time.time() - start_time < 300: 
            query = db.collection('tasks').where("status", "==", "pending").order_by("createdAt").limit(1).get()
            
            if not query:
                await asyncio.sleep(5) # Task မရှိရင် ၅ စက္ကန့် စောင့်ပြီး ပြန်စစ်မယ်
                continue
                
            doc = query[0]
            data = doc.to_dict()
            doc.reference.update({'status': 'processing'})
            print(f"🎬 Processing: {data.get('name')}")
            
            try:
                target = "movie.mp4"
                if data['type'] == 'video':
                    await app.download_media(data['value'], file_name=target)
                else:
                    url = data['value']
                    if 'drive.google.com' in url:
                        gdown.download(url, target, quiet=False, fuzzy=True)
                    else:
                        subprocess.run(f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" "{url}" -o {target}', shell=True)
                
                if not os.path.exists(target): raise Exception("Download Failed")

                # အပိုင်းဖြတ်ခြင်း
                split_s = int(data['len']) * 60
                subprocess.run(f'ffmpeg -i {target} -c copy -f segment -segment_time {split_s} -reset_timestamps 1 "p_%d.mp4"', shell=True)
                
                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(x.split('_')[1].split('.')[0]))
                
                for i, p in enumerate(parts):
                    out = f"final_{i}.mp4"
                    wm = data.get('wm', '')
                    if wm:
                        vf = f"drawtext=text='{wm}':fontcolor=white:fontsize=h/20:x=10:y=10"
                        subprocess.run(f'ffmpeg -y -i "{p}" -vf "{vf}" -c:v libx264 -crf 23 -c:a copy {out}', shell=True)
                    else:
                        os.rename(p, out)
                    
                    await app.send_video(data['user_id'], video=out, caption=f"{data['name']} Part {i+1}")
                    if os.path.exists(p): os.remove(p)
                    os.remove(out)

                os.remove(target)
                doc.reference.update({'status': 'completed'})
            except Exception as e:
                print(f"❌ Error: {e}")
                doc.reference.update({'status': 'error', 'error_msg': str(e)})

if __name__ == "__main__":
    asyncio.run(process_video())
