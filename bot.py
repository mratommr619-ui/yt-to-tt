import os, json, asyncio, subprocess, firebase_admin, time, re
from firebase_admin import credentials, firestore
from pyrogram import Client

# Firebase Setup
cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def process_video():
    # Login Flood မဖြစ်အောင် အပြင်မှာ တစ်ခါပဲ Authorize လုပ်မယ်
    async with Client("worker", int(os.environ.get("API_ID")), os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN")) as app:
        print("🚀 Worker started. Sequential processing mode is active.")
        
        # GitHub Action တစ်ခါတက်ရင် ၆ နာရီ (စက္ကန့် ၂၀၀၀၀) အထိ အပြင်မထွက်ဘဲ စောင့်မယ်
        start_runtime = time.time()
        while time.time() - start_runtime < 21000:
            
            # ၁။ Processing ဖြစ်နေတာ အရင်ယူ၊ မရှိမှ Pending ကိုယူမယ် (Queue System)
            active_task = db.collection('tasks').where("status", "==", "processing").order_by("createdAt").limit(1).get()
            if not active_task:
                active_task = db.collection('tasks').where("status", "==", "pending").order_by("createdAt").limit(1).get()
            
            if not active_task:
                await asyncio.sleep(20) # Task မရှိရင် ခဏစောင့်မယ်
                continue
            
            doc = active_task[0]
            data = doc.to_dict()
            uid = data['user_id']
            last_sent = data.get('last_sent_index', -1)
            
            try:
                doc.reference.update({'status': 'processing'})
                target = "movie.mp4"
                print(f"🎬 Working on: {data.get('name')} for User: {uid}")

                # ၂။ ဒေါင်းလော့ဆွဲခြင်း
                if data['type'] == 'video':
                    await app.download_media(data['value'], file_name=target)
                else:
                    # yt-dlp version error ကင်းအောင် list format နဲ့ သုံးမယ်
                    subprocess.run(['yt-dlp', '-f', 'mp4', '--no-check-certificate', '-o', target, data['value']], check=True)

                if not os.path.exists(target): raise Exception("File Download Failed")

                # ၃။ အပိုင်းဖြတ်ခြင်း (မူရင်းကို ချက်ချင်းဖျက်မယ်)
                split_s = int(data.get('len', 5)) * 60
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                if os.path.exists(target): os.remove(target)
                
                # အပိုင်းများကို နံပါတ်စဉ်အလိုက် စီမယ်
                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(re.search(r'\d+', x).group()))
                
                for i, p in enumerate(parts):
                    # Checkpoint: ပို့ပြီးသားဆို ကျော်မယ်
                    if i <= last_sent:
                        if os.path.exists(p): os.remove(p)
                        continue
                    
                    out = f"final_{i}.mp4"
                    wm = data.get('wm', '')
                    
                    # ၄။ Watermark & Encode (Syntax fix: libx264 ကို string ထဲ ထည့်ထားသည်)
                    if wm:
                        vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                        subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                    else:
                        os.rename(p, out)
                    
                    # ၅။ ပို့ခြင်းနှင့် Checkpoint မှတ်ခြင်း
                    if os.path.exists(out):
                        await app.send_video(uid, video=out, caption=f"{data.get('name')} Part {i+1}")
                        doc.reference.update({'last_sent_index': i})
                        os.remove(out)
                    if os.path.exists(p): os.remove(p)

                # ၆။ Task အားလုံးပြီးမှ Completed လုပ်မယ်
                doc.reference.update({'status': 'completed'})
                print(f"✅ Finished Task: {data.get('name')}")

            except Exception as e:
                print(f"❌ Error occurred: {e}")
                # Error တက်ရင်လည်း မသေအောင် ၃၀ စက္ကန့် စောင့်ပြီး နောက် task ပြန်ရှာမယ်
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(process_video())
