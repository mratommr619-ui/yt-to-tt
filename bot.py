import os, json, asyncio, subprocess, firebase_admin, time, re
from firebase_admin import credentials, firestore
from pyrogram import Client

# Firebase Setup
cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def process_video():
    async with Client("worker", int(os.environ.get("API_ID")), os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN")) as app:
        print("🚀 Worker started. Resume & Persistence mode active.")
        
        start_runtime = time.time()
        while time.time() - start_runtime < 21000: # ၆ နာရီ loop
            
            # ၁။ အစဉ်အတိုင်း Task ယူမယ်
            active_task = db.collection('tasks').where("status", "==", "processing").order_by("createdAt").limit(1).get()
            if not active_task:
                active_task = db.collection('tasks').where("status", "==", "pending").order_by("createdAt").limit(1).get()
            
            if not active_task:
                await asyncio.sleep(20); continue
            
            doc = active_task[0]; data = doc.to_dict(); uid = data['user_id']
            task_ref = doc.reference
            
            try:
                task_ref.update({'status': 'processing'})
                last_sent = data.get('last_sent_index', -1)
                target = "movie.mp4"
                
                print(f"🎬 Processing: {data.get('name')} | Resume from index: {last_sent}")

                # ၂။ GitHub ပြန်တက်လာရင် Disk က အမြဲအလွတ်မို့လို့ အမြဲ ပြန်ဒေါင်းရမယ်
                print(f"📥 Downloading source video...")
                if data['type'] == 'video':
                    await app.download_media(data['value'], file_name=target)
                else:
                    subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '--no-check-certificate', '-o', target, data['value']], check=True)

                if not os.path.exists(target): raise Exception("Download Failed")

                # ၃။ အပိုင်းတွေ ပြန်ခွဲမယ် (Disk မှာ ဘာမှမကျန်ခဲ့လို့ အမြဲပြန်ခွဲရမယ်)
                print("✂️ Re-splitting video into parts...")
                split_s = int(data.get('len', 5)) * 60
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                
                if os.path.exists(target): os.remove(target)

                # ၄။ အပိုင်းများကို စီမယ်
                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(re.search(r'\d+', x).group()))
                total_parts = len(parts)

                for i, p in enumerate(parts):
                    # --- [အဓိက Resume Checkpoint Logic] ---
                    # အရင်က ပို့ပြီးသား အပိုင်းဆိုရင် လုံးဝထပ်မပို့ဘဲ ချက်ချင်းဖျက်ပြီး Space ချန်မယ်
                    if i <= last_sent:
                        if os.path.exists(p): os.remove(p)
                        continue
                    
                    # မပို့ရသေးတဲ့ အပိုင်းတွေကိုပဲ ပြင်ဆင်ပြီး ပို့မယ်
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
                        
                        await app.send_video(uid, video=out, caption=caption_text)
                        
                        # ၅။ Firestore မှာ Checkpoint မှတ်မယ်
                        task_ref.update({'last_sent_index': i})
                        os.remove(out)
                    
                    if os.path.exists(p): os.remove(p)

                # ၆။ Task အားလုံးပြီးမှ Completed
                task_ref.update({'status': 'completed'})
                print(f"✅ Successfully finished for {uid}")

            except Exception as e:
                print(f"❌ Error: {e}")
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(process_video())
