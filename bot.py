import os, json, asyncio, subprocess, firebase_admin, time, re, requests
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession

# Firebase Setup
cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

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
        print("✅ Universal Downloader is active. Sorting logic fixed.")
        
        start_runtime = time.time()
        while time.time() - start_runtime < 21000:
            task = db.collection('tasks').where("status", "in", ["pending", "processing"]).limit(1).get()
            if not task:
                await asyncio.sleep(15); continue
            
            doc = task[0]; data = doc.to_dict(); target_uid = int(data['user_id'])
            task_ref = doc.reference
            
            try:
                task_ref.update({'status': 'processing'})
                last_sent = data.get('last_sent_index', -1)
                source_value = data.get('value', '').strip()
                target = "movie.mp4"
                
                if not os.path.exists(target):
                    print(f"📥 Target Source: {source_value}")

                    # --- ခွဲခြားဒေါင်းမယ့် Logic ---
                    
                    # ၁။ Telegram Link ဖြစ်နေရင် (ဥပမာ t.me/channel/123)
                    if "t.me/" in source_value:
                        print("📱 Telegram Link Detected. Using Telethon...")
                        parts = source_value.split('/')
                        msg_id = int(parts[-1])
                        chat = parts[-2]
                        await client.download_media(await client.get_messages(chat, ids=msg_id), target)

                    # ၂။ Telegram File ID ဖြစ်နေရင် (BAACAg...)
                    elif source_value.startswith('BAACAg'):
                        print("🆔 Telegram File ID Detected. Using Telethon...")
                        await client.download_media(source_value, target)

                    # ၃။ ကျန်တဲ့ Link အားလုံး (YouTube, Drive, etc.)
                    else:
                        print("🌐 External Link Detected. Using yt-dlp...")
                        # yt-dlp နဲ့ ဒေါင်းတဲ့အခါ Error တက်ရင် ချက်ချင်း သိရအောင် try-except ထပ်အုပ်မယ်
                        subprocess.run([
                            'yt-dlp', '-f', 'b[ext=mp4]/best', 
                            '--no-check-certificate', '-o', target, source_value
                        ], check=True)

                if os.path.exists(target):
                    print(f"✅ Success! Size: {os.path.getsize(target)/1024/1024:.1f}MB")
                    
                    # Splitting
                    split_s = int(data.get('len', 5)) * 60
                    subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_start_number', '1', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                    if os.path.exists(target): os.remove(target)

                    parts = [f for f in os.listdir('.') if f.startswith('p_') and f.endswith('.mp4')]
                    parts.sort(key=lambda x: int(re.search(r'\d+', x).group()))

                    for p in parts:
                        num = int(re.search(r'\d+', p).group())
                        if num <= last_sent:
                            os.remove(p); continue
                        
                        out = f"final_{num}.mp4"
                        wm = data.get('wm', '')
                        if wm:
                            vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                            subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                        else:
                            os.rename(p, out)
                        
                        await client.send_file(target_uid, out, caption=f"{data.get('name')} Part {num}", supports_streaming=True)
                        task_ref.update({'last_sent_index': num})
                        os.remove(out); os.remove(p)

                    task_ref.update({'status': 'completed'})
                else:
                    raise Exception("File not downloaded.")

            except Exception as e:
                print(f"❌ Error: {e}")
                task_ref.update({'status': 'failed', 'error': str(e)})
                await asyncio.sleep(20)

if __name__ == "__main__":
    asyncio.run(process_video())
