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
        print("🚀 Worker started. Persistence mode active.")
        
        start_runtime = time.time()
        while time.time() - start_runtime < 21000: # ၆ နာရီ loop
            
            # ၁။ Processing သမားကို အရင်ကြည့်၊ မရှိမှ Pending ကိုယူ
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
            
            # --- [အရေးကြီး] ဤနေရာမှစ၍ အပိုင်းအားလုံး ပို့မပြီးမချင်း Loop အစကို လုံးဝပြန်မသွားစေရ ---
            try:
                task_ref.update({'status': 'processing'})
                last_sent = data.get('last_sent_index', -1)
                target = "movie.mp4"
                
                # ၂။ ပြန်ဒေါင်းခြင်း (Disk အမြဲရှင်းနေမှာမို့လို့ Action အသစ်တက်တိုင်း ပြန်ဒေါင်းရမှာပဲ)
                print(f"📥 Downloading: {data.get('name')}")
                if data['type'] == 'video':
                    await app.download_media(data['value'], file_name=target)
                else:
                    subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '--no-check-certificate', '-o', target, data['value']], check=True)

                if not os.path.exists(target):
                    raise Exception("Download Failed")

                # ၃။ အပိုင်းပြန်ခွဲခြင်း
                print("✂️ Splitting video into parts...")
                split_s = int(data.get('len', 5)) * 60
                subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                
                # ဖြတ်ပြီးတာနဲ့ မူရင်းဖိုင်ကြီးကို ချက်ချင်းဖျက် (Disk Space အတွက်)
                if os.path.exists(target): os.remove(target)

                # ၄။ အပိုင်းများကို စီမယ်
                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(re.search(r'\d+', x).group()))
                total_parts = len(parts)
                print(f"📦 Total parts found: {total_parts}. Resuming after index {last_sent}...")

                # --- [ဤနေရာတွင် အပိုင်းတစ်ခုချင်းစီကို အဆုံးထိ ပို့မည်] ---
                for i, p in enumerate(parts):
                    # Checkpoint logic: ပို့ပြီးသားဆို ကျော်မယ်
                    if i <= last_sent:
                        if os.path.exists(p): os.remove(p)
                        continue
                    
                    out = f"final_{i}.mp4"
                    wm = data.get('wm', '')
                    
                    # ၅။ Watermark & Encode
                    if wm:
                        vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                        subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                    else:
                        os.rename(p, out)
                    
                    if os.path.exists(out):
                        caption_text = f"{data.get('name')} Part {i+1}"
                        if i == total_parts - 1:
                            caption_text += " (End Part) ✅"
                        
                        print(f"📤 Sending Part {i+1}/{total_parts} to {uid}...")
                        await app.send_video(uid, video=out, caption=caption_text)
                        
                        # Firestore Checkpoint ကို အပိုင်းတစ်ခု ပို့ပြီးတိုင်း update လုပ်မယ်
                        task_ref.update({'last_sent_index': i})
                        os.remove(out)
                    
                    if os.path.exists(p): os.remove(p)

                # ၆။ အပိုင်းအားလုံး ပို့ပြီးမှသာ status ကို completed ပြောင်းမယ်
                task_ref.update({'status': 'completed'})
                print(f"✅ Mission Accomplished: {data.get('name')}")

            except Exception as e:
                print(f"❌ Critical Error: {e}")
                # Error တက်ရင် ၃၀ စက္ကန့် စောင့်ပြီးမှ Loop အစကို ပြန်သွားမယ်
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(process_video())
