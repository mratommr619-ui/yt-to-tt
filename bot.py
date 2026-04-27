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
    bot_token = os.environ.get("TELEGRAM_TOKEN")

    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.start(bot_token=bot_token)
    
    async with client:
        print("🚀 Sequential Processing Started...")
        
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
                # database မှာ last_sent_index က 0 ဆိုရင် part 1 ပို့ပြီးသားလို့ မှတ်မယ်
                last_sent = data.get('last_sent_index', -1) 
                target = "movie.mp4"
                
                if not os.path.exists(target):
                    print(f"📥 Downloading: {data.get('name')}")
                    if data['type'] == 'video':
                        await client.download_media(data['value'], target)
                    else:
                        subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '--no-check-certificate', '-o', target, data['value']], check=True)

                # --- Split logic ပြင်ဆင်ခြင်း ---
                print("✂️ Splitting video into parts (Starting from 1)...")
                split_s = int(data.get('len', 5)) * 60
                # -segment_start_number 1 ထည့်လိုက်လို့ p_1.mp4 ကနေ စထွက်လာပါလိမ့်မယ်
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_start_number', '1', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                if os.path.exists(target): os.remove(target)

                # ဖိုင်တွေကို ရှာပြီး နံပါတ်စဉ်အလိုက် စီမယ်
                parts_files = [f for f in os.listdir('.') if f.startswith('p_') and f.endswith('.mp4')]
                # p_1, p_2, p_10 ဆိုတာမျိုးကို နံပါတ်အတိုင်း အတိအကျ စီမယ်
                parts_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
                total_parts = len(parts_files)

                for p in parts_files:
                    # ဖိုင်နာမည်ကနေ part number ယူမယ် (p_1.mp4 ဆိုရင် num က 1 ဖြစ်မယ်)
                    num = int(re.search(r'\d+', p).group())
                    
                    # ပို့ပြီးသားလား စစ်မယ် (last_sent က num ထက်ကြီးနေရင် ပို့ပြီးသား)
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
                        caption_text = f"{data.get('name')} Part {num}"
                        if num == total_parts: caption_text += " (End Part) ✅"
                        
                        print(f"📤 Sending Part {num} to {uid}...")
                        await client.send_file(uid, out, caption=caption_text, supports_streaming=True)
                        
                        # Database မှာ ဒီ part number ကို ပို့ပြီးကြောင်း မှတ်မယ်
                        task_ref.update({'last_sent_index': num})
                        os.remove(out)
                    
                    if os.path.exists(p): os.remove(p)

                task_ref.update({'status': 'completed'})
                print(f"✅ Finished task for {uid}")

            except Exception as e:
                print(f"❌ Error: {e}")
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(process_video())
