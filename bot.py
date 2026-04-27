import os, json, asyncio, subprocess, firebase_admin, time, re
from firebase_admin import credentials, firestore
from pyrogram import Client

cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def process_video():
    async with Client("worker", int(os.environ.get("API_ID")), os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN")) as app:
        print("🚀 Worker started. Priority: One task at a time.")
        
        start_time = time.time()
        while time.time() - start_time < 20000: # ၅ နာရီခွဲခန့် loop
            
            # ၁။ အရင်ဆုံး လုပ်လက်စ (processing) ရှိရင် အဲ့ဒါကို အရင်ယူ၊ မရှိမှ pending ကို ယူမယ်
            active_task = db.collection('tasks').where("status", "==", "processing").order_by("createdAt").limit(1).get()
            
            if not active_task:
                active_task = db.collection('tasks').where("status", "==", "pending").order_by("createdAt").limit(1).get()
            
            if not active_task:
                await asyncio.sleep(10); continue
            
            doc = active_task[0]
            data = doc.to_dict()
            uid = data['user_id']
            last_sent = data.get('last_sent_index', -1)
            
            try:
                # အလုပ်စပြီ (သို့) ပြန်စပြီလို့ မှတ်မယ်
                doc.reference.update({'status': 'processing'})
                
                target = "movie.mp4"
                print(f"🎬 Processing for {uid}. URL: {data['value']}")

                # ၂။ ဒေါင်းလော့ဆွဲခြင်း
                if data['type'] == 'video':
                    await app.download_media(data['value'], file_name=target)
                else:
                    subprocess.run(['yt-dlp', '-f', 'mp4', '--no-check-certificate', '-o', target, data['value']], check=True)

                if not os.path.exists(target): raise Exception("Download Failed")

                # ၃။ အပိုင်းဖြတ်ခြင်း
                split_s = int(data.get('len', 5)) * 60
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                
                os.remove(target) # Disk space ချန်ရန် မူရင်းကို ချက်ချင်းဖျက်
                
                # အပိုင်းများကို နာမည်စဉ်အတိုင်း စီမည်
                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(re.search(r'\d+', x).group()))
                
                for i, p in enumerate(parts):
                    # --- [Checkpoint Logic] ---
                    if i <= last_sent:
                        if os.path.exists(p): os.remove(p)
                        continue
                    
                    out = f"final_{i}.mp4"
                    wm = data.get('wm', '')
                    
                    # ၄။ ပြင်ဆင်/ပို့/ဖျက်
                    if wm:
                        vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                        subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                    else:
                        os.rename(p, out)
                    
                    if os.path.exists(out):
                        await app.send_video(uid, video=out, caption=f"{data.get('name')} Part {i+1}")
                        # Firestore မှာ Checkpoint မှတ်မယ်
                        doc.reference.update({'last_sent_index': i})
                        os.remove(out)
                    
                    if os.path.exists(p): os.remove(p)

                # ၅။ အကုန်ပြီးမှ status ကို completed ပြောင်းမယ်
                doc.reference.update({'status': 'completed'})
                print(f"✅ All parts sent for {uid}")

            except Exception as e:
                print(f"❌ Error during processing: {e}")
                # Error တက်ရင် processing အတိုင်းထားခဲ့မယ်၊ နောက်တစ်ခါ loop ပြန်ပတ်ရင် ဒီကောင်ကိုပဲ ပြန်ကိုင်မယ်
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(process_video())
