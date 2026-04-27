import os, json, asyncio, subprocess, firebase_admin, time, re
from firebase_admin import credentials, firestore
from telethon import TelegramClient, functions, types
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

    # connection_retries တိုးထားမယ်
    client = TelegramClient(StringSession(session_str), api_id, api_hash, connection_retries=10)
    
    # [အရေးကြီး] Bot အနေနဲ့ အလုပ်လုပ်ဖို့ သေချာအောင် start ကို await လုပ်မယ်
    await client.start(bot_token=bot_token)
    
    async with client:
        print("✅ Bot is fully authorized. Monitoring tasks...")
        
        start_runtime = time.time()
        while time.time() - start_runtime < 21000:
            active_task = db.collection('tasks').where("status", "==", "processing").order_by("createdAt").limit(1).get()
            if not active_task:
                active_task = db.collection('tasks').where("status", "==", "pending").order_by("createdAt").limit(1).get()
            
            if not active_task:
                await asyncio.sleep(20); continue
            
            doc = active_task[0]; data = doc.to_dict()
            target_uid = int(data['user_id']) # ပို့ရမယ့်သူ့ ID
            task_ref = doc.reference
            
            try:
                task_ref.update({'status': 'processing'})
                last_sent = data.get('last_sent_index', -1)
                target = "movie.mp4"
                
                # ၁။ တစ်ခါပဲ ဒေါင်းမယ်
                if not os.path.exists(target):
                    print(f"📥 Downloading source for {target_uid}...")
                    if data['type'] == 'video':
                        await client.download_media(data['value'], target)
                    else:
                        subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '--no-check-certificate', '-o', target, data['value']], check=True)

                if not os.path.exists(target): raise Exception("Download Failed")

                # ၂။ အပိုင်းပိုင်းမယ် (Part 1 ကနေ စမယ်)
                print("✂️ Splitting video...")
                split_s = int(data.get('len', 5)) * 60
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_start_number', '1', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                if os.path.exists(target): os.remove(target)

                # ၃။ ဖိုင်တွေကို နံပါတ်စဉ်အလိုက် စီမယ်
                parts = [f for f in os.listdir('.') if f.startswith('p_') and f.endswith('.mp4')]
                parts.sort(key=lambda x: int(re.search(r'\d+', x).group()))
                total_parts = len(parts)

                for p in parts:
                    num = int(re.search(r'\d+', p).group())
                    
                    # ပို့ပြီးသားလား စစ်မယ်
                    if num <= last_sent:
                        if os.path.exists(p): os.remove(p)
                        continue
                    
                    print(f"⚙️ Processing Part {num}...")
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
                        
                        # ၄။ [အဓိကအချက်] Saved Messages ထဲ မရောက်အောင် အတင်းအကျပ် ပို့ခိုင်းမယ်
                        print(f"📤 Sending Part {num} directly to User {target_uid}...")
                        
                        # InputPeerUser သုံးပြီး Target ဆီကိုပဲ အရောက်ပို့မယ်
                        entity = await client.get_input_entity(target_uid)
                        await client.send_file(
                            entity, 
                            out, 
                            caption=caption_text, 
                            supports_streaming=True
                        )
                        
                        task_ref.update({'last_sent_index': num})
                        os.remove(out)
                    
                    if os.path.exists(p): os.remove(p)

                task_ref.update({'status': 'completed'})
                print(f"✅ Task Finished for {target_uid}")

            except Exception as e:
                print(f"❌ Error: {e}")
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(process_video())
