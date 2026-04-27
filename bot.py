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

    if not session_str:
        print("❌ Error: SESSION_STRING missing in Secrets!")
        return

    # Client ကို တည်ဆောက်ပြီး Bot အနေနဲ့ Start လုပ်မယ်
    client = TelegramClient(StringSession(session_str), api_id, api_hash, connection_retries=10)
    
    # AuthKeyDuplicatedError မတက်အောင် connect အရင်လုပ်ပြီးမှ start စစ်မယ်
    await client.connect()
    if not await client.is_user_authorized():
        await client.start(bot_token=bot_token)

    async with client:
        print("✅ Bot is Online. Sequential processing engine started.")
        
        start_runtime = time.time()
        # ၅ နာရီခွဲ (GitHub Action limit နီးပါး) အထိ အလုပ်လုပ်မယ်
        while time.time() - start_runtime < 20000:
            # Task ရှာမယ် (Processing အရင်ကြည့်၊ မရှိရင် Pending ကြည့်)
            active_task = db.collection('tasks').where("status", "==", "processing").order_by("createdAt").limit(1).get()
            if not active_task:
                active_task = db.collection('tasks').where("status", "==", "pending").order_by("createdAt").limit(1).get()
            
            if not active_task:
                await asyncio.sleep(20)
                continue
            
            doc = active_task[0]
            data = doc.to_dict()
            target_uid = int(data['user_id'])
            task_ref = doc.reference
            
            try:
                task_ref.update({'status': 'processing'})
                last_sent = data.get('last_sent_index', -1)
                target = "movie.mp4"
                
                # ၁။ ဗီဒီယို တစ်ခါပဲ ဒေါင်းမယ်
                if not os.path.exists(target):
                    print(f"📥 Downloading: {data.get('name')} for {target_uid}")
                    if data['type'] == 'video':
                        await client.download_media(data['value'], target)
                    else:
                        subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '--no-check-certificate', '-o', target, data['value']], check=True)

                if not os.path.exists(target):
                    raise Exception("Source Download Failed!")

                # ၂။ ဗီဒီယို အပိုင်းပိုင်းမယ် (Part 1 ကနေ စမယ်)
                print("✂️ Splitting video into parts...")
                split_min = int(data.get('len', 5))
                subprocess.run([
                    'ffmpeg', '-y', '-i', target, 
                    '-c', 'copy', '-f', 'segment', 
                    '-segment_start_number', '1', 
                    '-segment_time', str(split_min * 60), 
                    '-reset_timestamps', '1', 'p_%d.mp4'
                ], check=True)
                
                # မူရင်းဖိုင်ကြီးကို နေရာလွတ်အောင် ချက်ချင်းဖျက်
                if os.path.exists(target): os.remove(target)

                # ၃။ ဖိုင်တွေကို နံပါတ်စဉ်အလိုက် အတိအကျစီမယ် (p_1, p_2, p_10...)
                all_parts = [f for f in os.listdir('.') if f.startswith('p_') and f.endswith('.mp4')]
                all_parts.sort(key=lambda x: int(re.search(r'\d+', x).group()))
                total_parts = len(all_parts)
                print(f"📦 Total parts to send: {total_parts}")

                # ၄။ တစ်ပိုင်းချင်းစီကို Watermark တပ်၊ ပို့၊ ပြီးရင်ဖျက်
                for p_file in all_parts:
                    p_num = int(re.search(r'\d+', p_file).group())
                    
                    # ပို့ပြီးသားအပိုင်းဆိုရင် ကျော်ပြီး ဖျက်ပစ်မယ်
                    if p_num <= last_sent:
                        if os.path.exists(p_file): os.remove(p_file)
                        continue
                    
                    print(f"⚙️ Processing Part {p_num}...")
                    final_output = f"final_{p_num}.mp4"
                    watermark_text = data.get('wm', '')
                    
                    if watermark_text:
                        # Watermark တပ်ရင် Re-encode လုပ်မယ်
                        vf_str = f"drawtext=text='{watermark_text}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                        subprocess.run([
                            'ffmpeg', '-y', '-i', p_file, 
                            '-vf', vf_str, '-c:v', 'libx264', 
                            '-crf', '23', '-c:a', 'copy', final_output
                        ], check=True)
                    else:
                        # Watermark မရှိရင် Rename လုပ်ပြီး တန်းပို့မယ်
                        os.rename(p_file, final_output)
                    
                    if os.path.exists(final_output):
                        caption = f"{data.get('name')} Part {p_num}"
                        if p_num == total_parts:
                            caption += " (End Part) ✅"
                        
                        # ၅။ User ဆီကို တိုက်ရိုက်ပို့မယ် (Saved Messages မဟုတ်စေရ)
                        print(f"📤 Sending Part {p_num} to User {target_uid}...")
                        user_entity = await client.get_input_entity(target_uid)
                        await client.send_file(
                            user_entity, 
                            final_output, 
                            caption=caption, 
                            supports_streaming=True
                        )
                        
                        # Database မှာ မှတ်တမ်းတင်ပြီး ဖိုင်ကို ချက်ချင်းဖျက်မယ်
                        task_ref.update({'last_sent_index': p_num})
                        os.remove(final_output)
                        print(f"🗑️ Cleaned up Part {p_num}")

                    if os.path.exists(p_file): os.remove(p_file)

                # ၆။ Task တစ်ခုလုံး ပြီးဆုံးကြောင်း မှတ်မယ်
                task_ref.update({'status': 'completed'})
                print(f"✅ Fully Finished Task for User {target_uid}")

            except Exception as e:
                print(f"❌ Task Error: {e}")
                # Error တက်ရင် ခဏနားပြီး နောက် Task ဆက်ကြည့်မယ်
                await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(process_video())
