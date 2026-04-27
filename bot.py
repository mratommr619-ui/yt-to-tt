import os, json, asyncio, subprocess, firebase_admin, time, re, requests
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession

# Firebase Setup
cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

# ၁။ ဘာသာစကားအလိုက် စာသားများ (my နဲ့ en)
TEXTS = {
    'en': {
        'start_dl': "📥 Downloading your video, please wait...",
        'dl_fail': "❌ Download failed. The link might be broken or private.",
        'sending': "📤 Sending Part {num}...",
        'end_part': " (End Part) ✅",
        'error': "❌ An error occurred: "
    },
    'my': {
        'start_dl': "📥 ဗီဒီယိုကို ဒေါင်းလုဒ်ဆွဲနေပါတယ်၊ ခဏစောင့်ပေးပါ...",
        'dl_fail': "❌ ဒေါင်းလုဒ်ဆွဲလို့ မရပါဘူး။ Link ပျက်နေတာ (သို့) Private ဖြစ်နေတာ ဖြစ်နိုင်ပါတယ်။",
        'sending': "📤 အပိုင်း {num} ကို ပို့နေပါတယ်...",
        'end_part': " (ဇာတ်သိမ်းပိုင်း) ✅",
        'error': "❌ အမှားတစ်ခု ဖြစ်သွားပါတယ်: "
    }
}

def resolve_url(url):
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        return response.url
    except:
        return url

def parse_duration(duration_str):
    """မိနစ်:စက္ကန့် (3:30) သို့မဟုတ် မိနစ် (3.5) ကို စက္ကန့်အဖြစ် ပြောင်းပေးခြင်း"""
    try:
        duration_str = str(duration_str).strip()
        if ':' in duration_str:
            parts = duration_str.split(':')
            if len(parts) == 2:
                # 3:30 -> 210s
                return int(float(parts[0]) * 60 + float(parts[1]))
        # 3.5 -> 210s
        return int(float(duration_str) * 60)
    except:
        return 300 # Default 5 mins

async def process_video():
    session_str = os.environ.get("SESSION_STRING")
    api_id = int(os.environ.get("API_ID"))
    api_hash = os.environ.get("API_HASH")
    bot_token = os.environ.get("TELEGRAM_TOKEN")

    client = TelegramClient(StringSession(session_str), api_id, api_hash, connection_retries=10)
    await client.connect()
    if not await client.is_user_authorized():
        await client.start(bot_token=bot_token)

    async with client:
        print("🚀 Worker is online. Multi-language (my/en) support active.")
        
        start_runtime = time.time()
        while time.time() - start_runtime < 21000:
            active_task = db.collection('tasks').where("status", "in", ["pending", "processing"]).limit(1).get()
            
            if not active_task:
                await asyncio.sleep(15); continue
            
            doc = active_task[0]; data = doc.to_dict(); target_uid = int(data['user_id'])
            task_ref = doc.reference
            
            # ဘာသာစကား သတ်မှတ်ချက် (my သို့မဟုတ် en)
            lang = data.get('lang', 'my')
            t = TEXTS.get(lang, TEXTS['my'])
            
            try:
                task_ref.update({'status': 'processing'})
                source_value = data.get('value', '').strip()
                target = "movie.mp4"
                
                # 📥 Universal Downloader
                if not os.path.exists(target):
                    print(f"📥 Downloading Source: {source_value[:30]}")
                    try:
                        if "t.me/" in source_value:
                            parts = source_value.split('/')
                            msg_id = int(parts[-1]); chat = parts[-2]
                            await client.download_media(await client.get_messages(chat, ids=msg_id), target)
                        elif source_value.startswith('BAACAg'):
                            await client.download_media(source_value, target)
                        else:
                            real_url = resolve_url(source_value)
                            subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/best', '--no-check-certificate', '-o', target, real_url], check=True)
                    except:
                        await client.send_message(target_uid, t['dl_fail'])
                        task_ref.delete(); continue

                if os.path.exists(target):
                    # ✂️ Split Logic (မိနစ်:စက္ကန့်ရော၊ ဒသမရော ရတယ်)
                    split_seconds = parse_duration(data.get('len', '5'))
                    subprocess.run(['ffmpeg', '-y', '-i', target, '-c', 'copy', '-f', 'segment', '-segment_start_number', '1', '-segment_time', str(split_seconds), '-reset_timestamps', '1', 'p_%d.mp4'], check=True)
                    if os.path.exists(target): os.remove(target)

                    # 📦 Sequential Sorting
                    parts = sorted([f for f in os.listdir('.') if f.startswith('p_') and f.endswith('.mp4')], key=lambda x: int(re.search(r'\d+', x).group()))
                    total_parts = len(parts)

                    for p in parts:
                        num = int(re.search(r'\d+', p).group())
                        if num <= data.get('last_sent_index', -1):
                            os.remove(p); continue
                        
                        out = f"final_{num}.mp4"
                        wm = data.get('wm', '')
                        
                        # Watermark
                        if wm:
                            vf = f"drawtext=text='{wm}':fontcolor=white@0.6:fontsize=h/15:x='if(gte(t,0),mod(t*100,w),0)':y='(h-text_h)/2 + sin(t)*100'"
                            subprocess.run(['ffmpeg', '-y', '-i', p, '-vf', vf, '-c:v', 'libx264', '-crf', '23', '-c:a', 'copy', out], check=True)
                        else:
                            os.rename(p, out)
                        
                        # Multi-language Caption
                        video_name = data.get('name', 'Video')
                        caption = f"{video_name} {t['sending'].format(num=num)}"
                        if num == total_parts: caption += t['end_part']
                        
                        user_entity = await client.get_input_entity(target_uid)
                        await client.send_file(user_entity, out, caption=caption, supports_streaming=True)
                        
                        # Update progress & Delete local file
                        task_ref.update({'last_sent_index': num})
                        os.remove(out); os.remove(p)

                    # ✅ အားလုံးပြီးရင် Firebase ကနေ Task ကို လုံးဝဖျက်မယ်
                    task_ref.delete()
                    print(f"✨ Task complete & data deleted for {target_uid}")
                else:
                    task_ref.delete()

            except Exception as e:
                print(f"❌ Error: {e}")
                try: await client.send_message(target_uid, f"{t['error']}{str(e)[:50]}")
                except: pass
                task_ref.delete() # Error ဖြစ်ရင်လည်း Firebase ရှင်းအောင် ဖျက်မယ်
                await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(process_video())
