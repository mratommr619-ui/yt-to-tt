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
        print("✅ Sequential Worker is active. No more syntax errors.")
        
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
                source_value = data.get('value', '')
                target = "movie.mp4"
                
                # ၁။ ဗီဒီယိုကို အရင်ဒေါင်းမယ်
                if not os.path.exists(target):
                    print(f"📥 Downloading source...")
                    if source_value.startswith('BAACAg'):
                        await client.download_media(source_value, target)
                    else:
                        real_url = resolve_url(source_value)
                        subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '--no-check-certificate', '-o', target, real_url], check=True)

                if os.path.exists(target):
                    # ၂။ အပိုင်းပိုင်းဖြတ်မယ် (Part 1 ကနေ စမယ်)
                    print("✂️ Splitting video...")
                    split_s = int(data.get('len', 5)) * 60
                    subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_start_number', '1', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                    if os.path.exists(target): os.remove(target)

                    # ၃။ ဖိုင်တွေကို နံပါတ်စဉ်အလိုက် စီမယ်
                    parts = [f for f in os.listdir('.') if f.startswith('p_') and f.endswith('.mp4')]
                    # Syntax Error ပြင်ဆင်ပြီးသား Line:
                    parts.sort(key=lambda x: int(re.search(r'\d+', x).group()))
                    total_parts = len(parts)

                    for p in parts:
                        num = int(re.search(r'\d+', p).group())
                        
                        # ပို့ပြီးသားလား စစ်မယ်
                        if num <= last_sent:
                            if os.path.exists(p): os.remove(p)
                            continue
                        
                        print(f"⚙️ Processing Part {num}/{total_parts}...")
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
                            
                            # User ဆီ အရောက်ပို့မယ်
                            await client.send_file(target_uid, out, caption=cap, supports_streaming=True)
                            
                            # Database Update လုပ်ပြီး ဖိုင်ဖျက်မယ်
                            task_ref.update({'last_sent_index': num})
                            os.remove(out)
                        if os.path.exists(p): os.remove(p)

                    task_ref.update({'status': 'completed'})
                    print(f"✅ Mission Success for {target_uid}")
                else:
                    task_ref.update({'status': 'failed'})

            except Exception as e:
                print(f"❌ Error: {e}")
                task_ref.update({'status': 'failed', 'error': str(e)})
                await asyncio.sleep(20)

if __name__ == "__main__":
    asyncio.run(process_video())
