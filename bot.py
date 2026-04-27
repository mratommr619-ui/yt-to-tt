import os, json, asyncio, subprocess, firebase_admin, time, re, requests
from firebase_admin import credentials, firestore
from telethon import TelegramClient, errors
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
    await client.connect()
    
    # Session Expire မဖြစ်အောင် Double Check
    if not await client.is_user_authorized():
        await client.start(bot_token=bot_token)

    async with client:
        print("✅ Bot starts working. No more errors hopefully!")
        
        start_runtime = time.time()
        while time.time() - start_runtime < 21000:
            task = db.collection('tasks').where("status", "in", ["pending", "processing"]).limit(1).get()
            
            if not task:
                await asyncio.sleep(15); continue
            
            doc = task[0]; data = doc.to_dict(); target_uid = int(data['user_id'])
            task_ref = doc.reference
            
            try:
                task_ref.update({'status': 'processing'})
                source_value = data.get('value', '')
                target = "movie.mp4"
                
                # ၁။ Telegram File ကို ပိုသေချာအောင် ဒေါင်းမယ်
                if not os.path.exists(target):
                    print(f"📥 Downloading from: {source_value[:15]}...")
                    
                    if source_value.startswith('BAACAg'):
                        # အကယ်၍ file_id နဲ့ တိုက်ရိုက်မရရင် Message Link လား စစ်မယ်
                        try:
                            await client.download_media(source_value, target)
                        except Exception as e:
                            print(f"⚠️ Direct ID download failed: {e}")
                            # နောက်တစ်နည်း: Link ကနေ ဒေါင်းဖို့ ကြိုးစားမယ် (မိတ်ဆွေ Bot ဆီ Forward လုပ်ထားရင် ရမယ်)
                            raise Exception("Telegram access denied for this File ID.")
                    else:
                        # YouTube, Drive or Direct Link
                        subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '--no-check-certificate', '-o', target, source_value], check=True)

                if os.path.exists(target):
                    print(f"✅ Downloaded ({os.path.getsize(target)/1024/1024:.1f}MB)")
                    
                    # ၂။ ဖြတ်မယ် (FFmpeg)
                    split_s = int(data.get('len', 5)) * 60
                    subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_start_number', '1', '-segment_time', str(split_s), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                    if os.path.exists(target): os.remove(target)

                    # ၃။ ပို့မယ်
                    parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(re.search(rr'\d+', x).group()))
                    for p in parts:
                        num = int(re.search(r'\d+', p).group())
                        if num <= data.get('last_sent_index', -1):
                            os.remove(p); continue
                        
                        out = f"final_{num}.mp4"
                        wm = data.get('wm', '')
                        if wm:
                            vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                            subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                        else:
                            os.rename(p, out)
                        
                        await client.send_file(target_uid, out, caption=f"{data.get('name')} Part {num}", supports_streaming=True)
                        task_ref.update({'last_sent_index': num})
                        os.remove(out); os.remove(p)

                    task_ref.update({'status': 'completed'})
                else:
                    task_ref.update({'status': 'failed'})

            except Exception as e:
                print(f"❌ Error: {e}")
                task_ref.update({'status': 'failed', 'error': str(e)})
                await asyncio.sleep(20)

if __name__ == "__main__":
    asyncio.run(process_video())
