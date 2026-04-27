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
        print("🚀 Worker started. Monitoring tasks with Checkpoint system...")
        
        start_time = time.time()
        while time.time() - start_time < 20000: # ၅ နာရီခွဲခန့် loop
            # တစ်ခါရင် တစ်ခုပဲယူမယ် (Queue System)
            query = db.collection('tasks').where("status", "in", ["pending", "processing"]).order_by("createdAt").limit(1).get()
            
            if not query:
                await asyncio.sleep(10); continue
            
            doc = query[0]
            data = doc.to_dict()
            uid = data['user_id']
            task_id = doc.id
            
            # လက်ရှိ ဘယ်အပိုင်းအထိ ပို့ပြီးပြီလဲ (Checkpoint)
            last_sent = data.get('last_sent_index', -1) 
            
            try:
                # အလုပ်စပြီလို့ မှတ်မယ်
                doc.reference.update({'status': 'processing'})
                
                target = "movie.mp4"
                # ၁။ ဒေါင်းလော့ဆွဲခြင်း
                if data['type'] == 'video':
                    await app.download_media(data['value'], file_name=target)
                else:
                    cmd = ['yt-dlp', '-f', 'b[ext=mp4]/b', '--no-check-certificate', '-o', target, data['value']]
                    subprocess.run(cmd, check=True)

                if not os.path.exists(target): raise Exception("Download Failed")

                # ၂။ အပိုင်းဖြတ်ခြင်း
                split_s = int(data.get('len', 5)) * 60
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                
                # မူရင်းဖိုင်ကို ချက်ချင်းဖျက် (Disk Space ချွေတာရန်)
                os.remove(target) 
                
                # အပိုင်းများကို စီမည်
                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(re.search(r'\d+', x).group()))
                
                for i, p in enumerate(parts):
                    # --- [Checkpoint Logic] ---
                    # အရင်က ပို့ပြီးသား အပိုင်းဆိုရင် ကျော်သွားမယ်
                    if i <= last_sent:
                        if os.path.exists(p): os.remove(p)
                        continue
                    
                    out = f"final_{i}.mp4"
                    wm = data.get('wm', '')
                    
                    # ၃။ တစ်ပိုင်းချင်းစီ ပြင်ဆင်ခြင်း
                    if wm:
                        vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                        subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                    else:
                        os.rename(p, out)
                    
                    # ၄။ ပို့ခြင်း
                    if os.path.exists(out):
                        await app.send_video(uid, video=out, caption=f"{data.get('name')} Part {i+1}")
                        # ၅။ Firestore မှာ Checkpoint မှတ်မယ်
                        doc.reference.update({'last_sent_index': i})
                        # ၆။ ပို့ပြီးသားဖိုင်ကို ချက်ချင်းဖျက်
                        os.remove(out)
                    
                    if os.path.exists(p): os.remove(p)

                # Task အောင်မြင်စွာ ပြီးဆုံးကြောင်း မှတ်မယ်
                doc.reference.update({'status': 'completed'})
                print(f"✅ Fully Completed for {uid}")

            except Exception as e:
                print(f"❌ Error: {e}")
                # GitHub Action သေသွားခဲ့ရင် status က processing မှာပဲ ကျန်ခဲ့မယ်
                # ဒါမှ နောက်တစ်ခါ Action ပြန်တက်လာရင် error မပြဘဲ အဲ့ဒီနေရာကနေ ပြန်စနိုင်မှာ
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(process_video())
