import os, json, asyncio, subprocess, firebase_admin, time, re
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
    bot_token = os.environ.get("TELEGRAM_TOKEN") # Bot Token လိုအပ်ပါတယ်

    # Connection retries ကို ၁၀ ကြိမ်ထားပြီး တည်ငြိမ်အောင် လုပ်မယ်
    client = TelegramClient(StringSession(session_str), api_id, api_hash, connection_retries=10)

    # --- [အရေးကြီးဆုံးအချက်] Bot အနေနဲ့ အလုပ်လုပ်ဖို့ start မှာ bot_token ထည့်ရပါမယ် ---
    async with client.start(bot_token=bot_token) as bot:
        print("✅ Bot Connected & Logged in as Bot Account.")
        
        start_runtime = time.time()
        while time.time() - start_runtime < 21000:
            active_task = db.collection('tasks').where("status", "==", "processing").order_by("createdAt").limit(1).get()
            if not active_task:
                active_task = db.collection('tasks').where("status", "==", "pending").order_by("createdAt").limit(1).get()
            
            if not active_task:
                await asyncio.sleep(20); continue
            
            doc = active_task[0]; data = doc.to_dict()
            # User ID ကို integer ဖြစ်အောင် သေချာပြောင်းမယ်
            uid = int(data['user_id']) 
            task_ref = doc.reference
            
            try:
                task_ref.update({'status': 'processing'})
                last_sent = data.get('last_sent_index', -1)
                target = "movie.mp4"
                
                print(f"📥 Downloading: {data.get('name')}")
                if not os.path.exists(target):
                    if data['type'] == 'video':
                        # Telegram ကနေ ဒေါင်းတာဆိုရင် bot object ကို သုံးမယ်
                        await bot.download_media(data['value'], target)
                    else:
                        # YouTube/Link ကဆိုရင် yt-dlp သုံးမယ်
                        subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '--no-check-certificate', '-o', target, data['value']], check=True)

                if not os.path.exists(target): raise Exception("Download Failed")

                print("✂️ Splitting video...")
                split_s = int(data.get('len', 5)) * 60
                # Split လုပ်တဲ့အခါ stream ပြန်မပွင့်တာမျိုး မဖြစ်အောင် -c copy သုံးထားပါတယ်
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
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
                        # Watermark ထည့်ရင် encode ပြန်လုပ်ရမှာမို့ libx264 သုံးမယ်
                        vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                        subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                    else:
                        # Watermark မရှိရင် မြန်အောင် rename ပဲ လုပ်မယ်
                        os.rename(p, out)
                    
                    if os.path.exists(out):
                        caption_text = f"{data.get('name')} Part {i+1}"
                        if i == total_parts - 1: caption_text += " (End Part) ✅"
                        
                        print(f"📤 Sending Part {i+1}/{total_parts} to {uid}...")
                        
                        # supports_streaming က player ထဲမှာ တန်းကြည့်လို့ရစေပါတယ်
                        await bot.send_file(
                            uid, 
                            out, 
                            caption=caption_text,
                            force_document=False, 
                            supports_streaming=True
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
