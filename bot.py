import os, json, asyncio, subprocess, firebase_admin, time, re
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeVideo

# Firebase Setup
cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def process_video():
    session_str = os.environ.get("SESSION_STRING")
    api_id = int(os.environ.get("API_ID"))
    api_hash = os.environ.get("API_HASH")

    # Telethon ကို fast upload ဖြစ်အောင် connection_retries တိုးထားမယ်
    client = TelegramClient(StringSession(session_str), api_id, api_hash, connection_retries=10)

    async with client:
        print("✅ Telethon Connected. Speed optimized mode active.")
        
        start_runtime = time.time()
        while time.time() - start_runtime < 21000:
            active_task = db.collection('tasks').where("status", "==", "processing").order_by("createdAt").limit(1).get()
            if not active_task:
                active_task = db.collection('tasks').where("status", "==", "pending").order_by("createdAt").limit(1).get()
            
            if not active_task:
                await asyncio.sleep(20); continue
            
            doc = active_task[0]; data = doc.to_dict(); uid = int(data['user_id'])
            task_ref = doc.reference
            
            try:
                task_ref.update({'status': 'processing'})
                last_sent = data.get('last_sent_index', -1)
                target = "movie.mp4"
                
                print(f"📥 Downloading: {data.get('name')}")
                # Download speed အတွက် yt-dlp ကိုပဲ ဆက်သုံးမယ်
                if data['type'] == 'video':
                    # Telegram က ဒေါင်းရင် အချိန်ကြာတတ်လို့ ဒါလေးပဲ သတိထားပါ
                    await client.download_media(data['value'], target)
                else:
                    subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '--no-check-certificate', '-o', target, data['value']], check=True)

                if not os.path.exists(target): raise Exception("Download Failed")

                print("✂️ Splitting video...")
                split_s = int(data.get('len', 5)) * 60
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c:v', 'copy', '-c:a', 'copy', '-f', 'segment', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                if os.path.exists(target): os.remove(target)

                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(re.search(r'\d+', x).group()))
                total_parts = len(parts)

                for i, p in enumerate(parts):
                    if i <= last_sent:
                        if os.path.exists(p): os.remove(p)
                        continue
                    
                    out = f"final_{i}.mp4"
                    wm = data.get('wm', '')
                    
                    if wm:
                        vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                        subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                    else:
                        os.rename(p, out)
                    
                    if os.path.exists(out):
                        caption_text = f"{data.get('name')} Part {i+1}"
                        if i == total_parts - 1: caption_text += " (End Part) ✅"
                        
                        print(f"📤 Sending Part {i+1}/{total_parts} (Optimized)...")
                        
                        # Telethon မှာ Video အဖြစ်ရောက်အောင် attributes ထည့်ပေးရမယ်
                        await client.send_file(
                            uid, 
                            out, 
                            caption=caption_text,
                            force_document=False, # Video အဖြစ် ပြမယ်
                            supports_streaming=True # Stream ကြည့်လို့ရအောင်
                        )
                        
                        task_ref.update({'last_sent_index': i})
                        os.remove(out)
                    if os.path.exists(p): os.remove(p)

                task_ref.update({'status': 'completed'})
                print(f"✅ Mission Success for {uid}")

            except Exception as e:
                print(f"❌ Error: {e}")
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(process_video())
