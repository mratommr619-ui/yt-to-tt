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
        print("🚀 Worker started. Sequential processing mode is active.")
        
        start_runtime = time.time()
        # ၆ နာရီနီးပါး အပြင်မထွက်ဘဲ Loop ပတ်မယ်
        while time.time() - start_runtime < 21000:
            
            # ၁။ အရင်ဆုံး Task တစ်ခုကို သေချာဆွဲထုတ်မယ်
            active_task = db.collection('tasks').where("status", "==", "processing").order_by("createdAt").limit(1).get()
            if not active_task:
                active_task = db.collection('tasks').where("status", "==", "pending").order_by("createdAt").limit(1).get()
            
            if not active_task:
                await asyncio.sleep(20)
                continue
            
            doc = active_task[0]
            data = doc.to_dict()
            uid = data['user_id']
            task_ref = doc.reference
            
            # --- [အရေးကြီး] ဤနေရာမှစ၍ Task တစ်ခုလုံး မပြီးမချင်း Loop အစကို ပြန်မသွားစေရပါ ---
            try:
                task_ref.update({'status': 'processing'})
                last_sent = data.get('last_sent_index', -1)
                target = "movie.mp4"
                
                print(f"🎬 Processing: {data.get('name')} for {uid}")

                # ၂။ ဒေါင်းလော့ (File ရှိပြီးသားဆို ထပ်မဒေါင်းတော့ဘူး)
                if not os.path.exists(target):
                    if data['type'] == 'video':
                        await app.download_media(data['value'], file_name=target)
                    else:
                        subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]', '--no-check-certificate', '-o', target, data['value']], check=True)

                if not os.path.exists(target): raise Exception("Download Failed")

                # ၃။ အပိုင်းဖြတ်ခြင်း (p_0.mp4 စသဖြင့် မရှိသေးမှ ဖြတ်မယ်)
                if not any(f.startswith('p_') for f in os.listdir('.')):
                    split_s = int(data.get('len', 5)) * 60
                    subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', segment, '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                
                if os.path.exists(target): os.remove(target) # မူရင်းကို အမြန်ဖျက်
                
                # ၄။ အပိုင်းများကို စီပြီး တစ်ခုချင်းစီ ပို့ခြင်း
                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(re.search(r'\d+', x).group()))
                
                for i, p in enumerate(parts):
                    # Checkpoint: ပို့ပြီးသားဆို ကျော်
                    if i <= last_sent:
                        if os.path.exists(p): os.remove(p)
                        continue
                    
                    out = f"final_{i}.mp4"
                    wm = data.get('wm', '')
                    
                    # Watermark ထည့်မယ်
                    if wm:
                        vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                        subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                    else:
                        os.rename(p, out)
                    
                    # ၅။ တကယ်ပို့တဲ့နေရာ (ဤနေရာရောက်မှ User ဆီ ဖိုင်ရောက်မှာပါ)
                    if os.path.exists(out):
                        await app.send_video(uid, video=out, caption=f"{data.get('name')} Part {i+1}")
                        # ပို့ပြီးတိုင်း Database မှာ အောင်မြင်ကြောင်း မှတ်မယ်
                        task_ref.update({'last_sent_index': i})
                        os.remove(out)
                    
                    if os.path.exists(p): os.remove(p)

                # ၆။ အားလုံးပြီးမှသာ Completed လုပ်ပြီး Task ကို အဆုံးသတ်မယ်
                task_ref.update({'status': 'completed'})
                print(f"✅ Fully Finished: {data.get('name')}")

            except Exception as e:
                print(f"❌ Error: {e}")
                await asyncio.sleep(30) # Error ဖြစ်ရင် ခေတ္တနားပြီးမှ Loop ပြန်စမယ်

if __name__ == "__main__":
    asyncio.run(process_video())
