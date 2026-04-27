import os, json, asyncio, subprocess, firebase_admin, time, re, requests
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession

# Firebase Setup
cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

def resolve_url(url):
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        return response.url
    except:
        return url

# Telegram ကနေ ဒေါင်းတဲ့အခါ Progress ပြဖို့ function
def progress_callback(current, total):
    print(f"📊 Download Progress: {current / 1024 / 1024:.2f}MB / {total / 1024 / 1024:.2f}MB ({(current / total) * 100:.1f}%)")

async def process_video():
    session_str = os.environ.get("SESSION_STRING")
    api_id = int(os.environ.get("API_ID"))
    api_hash = os.environ.get("API_HASH")
    bot_token = os.environ.get("TELEGRAM_TOKEN")

    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    
    # Session သေမသေ စစ်မယ်
    if not await client.is_user_authorized():
        print("⚠️ Session expired or invalid! Re-starting with Bot Token...")
        await client.start(bot_token=bot_token)

    async with client:
        print("🚀 Worker is running. Waiting for tasks...")
        
        start_runtime = time.time()
        while time.time() - start_runtime < 21000:
            task = db.collection('tasks').where("status", "==", "processing").limit(1).get()
            if not task: task = db.collection('tasks').where("status", "==", "pending").limit(1).get()
            
            if not task:
                await asyncio.sleep(15); continue
            
            doc = task[0]; data = doc.to_dict(); target_uid = int(data['user_id'])
            task_ref = doc.reference
            
            try:
                task_ref.update({'status': 'processing'})
                last_sent = data.get('last_sent_index', -1)
                source_value = data.get('value', '')
                target = "movie.mp4"
                
                if not os.path.exists(target):
                    print(f"🔎 Source found: {source_value[:20]}...")

                    # ၁။ Telegram File ဖြစ်နေရင်
                    if source_value.startswith('BAACAg'):
                        print("📥 Downloading directly from Telegram...")
                        # Progress callback ထည့်ထားလို့ GitHub Log မှာ ရာခိုင်နှုန်း တက်လာတာ မြင်ရပါလိမ့်မယ်
                        await client.download_media(source_value, target, progress_callback=progress_callback)
                    
                    # ၂။ URL ဖြစ်နေရင်
                    else:
                        real_url = resolve_url(source_value)
                        print(f"🔗 Downloading from URL: {real_url}")
                        subprocess.run([
                            'yt-dlp', '-f', 'b[ext=mp4]/best', 
                            '--no-check-certificate', '-o', target, real_url
                        ], check=True)

                if os.path.exists(target):
                    print(f"✅ Download Finished! File Size: {os.path.getsize(target) / 1024 / 1024:.2f} MB")
                    
                    # Split & Send Logic
                    split_s = int(data.get('len', 5)) * 60
                    subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_start_number', '1', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                    if os.path.exists(target): os.remove(target)

                    parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(re.search(r'\d+', x).group()))
                    
                    for p in parts:
                        num = int(re.search(r'\d+', p).group())
                        if num <= last_sent:
                            if os.path.exists(p): os.remove(p)
                            continue
                        
                        out = f"final_{num}.mp4"
                        wm = data.get('wm', '')
                        if wm:
                            vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                            subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                        else:
                            os.rename(p, out)
                        
                        if os.path.exists(out):
                            cap = f"{data.get('name')} Part {num}"
                            if num == len(parts): cap += " (End Part) ✅"
                            await client.send_file(target_uid, out, caption=cap, supports_streaming=True)
                            task_ref.update({'last_sent_index': num})
                            os.remove(out)
                        if os.path.exists(p): os.remove(p)

                    task_ref.update({'status': 'completed'})
                    print(f"✨ Task Completed for {target_uid}")
                else:
                    print("❌ File was not downloaded. Check the source ID/Link.")
                    task_ref.update({'status': 'failed'})

            except Exception as e:
                print(f"❌ Processing Error: {e}")
                # Error တက်ရင် Firebase မှာ status ကို pending ပြန်ပို့ထားမယ် (နောက်တစ်ခေါက် ပြန်ကြိုးစားဖို့)
                task_ref.update({'status': 'pending'})
                await asyncio.sleep(20)

if __name__ == "__main__":
    asyncio.run(process_video())
