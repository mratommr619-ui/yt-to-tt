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
    """Short URL တွေကို မူရင်း Link အရှည်ဖြစ်အောင် ဖြည်ပေးတဲ့ function"""
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        return response.url
    except:
        return url

async def process_video():
    session_str = os.environ.get("SESSION_STRING")
    api_id = int(os.environ.get("API_ID"))
    api_hash = os.environ.get("API_HASH")
    bot_token = os.environ.get("TELEGRAM_TOKEN")

    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.start(bot_token=bot_token)

    async with client:
        print("🚀 Universal Video Processor is Online...")
        
        start_runtime = time.time()
        while time.time() - start_runtime < 21000:
            task = db.collection('tasks').where("status", "==", "processing").limit(1).get()
            if not task: task = db.collection('tasks').where("status", "==", "pending").limit(1).get()
            
            if not task:
                await asyncio.sleep(20); continue
            
            doc = task[0]; data = doc.to_dict(); target_uid = int(data['user_id'])
            task_ref = doc.reference
            
            try:
                task_ref.update({'status': 'processing'})
                last_sent = data.get('last_sent_index', -1)
                source_value = data.get('value', '')
                target = "movie.mp4"
                
                if not os.path.exists(target):
                    print(f"📥 Attempting to download from source: {source_value[:30]}...")

                    # ၁။ Telegram File ဖြစ်နေရင် (BAACAg... နဲ့ စရင်)
                    if source_value.startswith('BAACAg'):
                        await client.download_media(source_value, target)
                    
                    # ၂။ အခြား Link တွေဖြစ်ရင် (URL)
                    else:
                        # Short URL ဖြည်မယ်
                        real_url = resolve_url(source_value)
                        print(f"🔗 Resolved URL: {real_url}")
                        
                        # yt-dlp နဲ့ ဒေါင်းမယ် (ဘာ Link လာလာ သူက handle လုပ်နိုင်တယ်)
                        # --no-check-certificate နဲ့ --location (redirects) တွေကို သုံးထားတယ်
                        cmd = [
                            'yt-dlp', 
                            '-f', 'b[ext=mp4]/best', 
                            '--no-check-certificate',
                            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                            '-o', target, 
                            real_url
                        ]
                        subprocess.run(cmd, check=True)

                if not os.path.exists(target): raise Exception("Download Failed!")

                # --- Split & Send Logic (အစဉ်လိုက် သွားမယ်) ---
                print("✂️ Splitting...")
                split_s = int(data.get('len', 5)) * 60
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_start_number', '1', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                if os.path.exists(target): os.remove(target)

                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(re.search(r'\d+', x).group()))
                total_parts = len(parts)

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
                        if num == total_parts: cap += " (End Part) ✅"
                        await client.send_file(target_uid, out, caption=cap, supports_streaming=True)
                        task_ref.update({'last_sent_index': num})
                        os.remove(out)
                    if os.path.exists(p): os.remove(p)

                task_ref.update({'status': 'completed'})
                print(f"✅ Finished task for {target_uid}")

            except Exception as e:
                print(f"❌ Error: {e}")
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(process_video())
