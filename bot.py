import os, base64, subprocess, asyncio, firebase_admin, json, re, shutil
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# 1. Firebase Initializer
if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if cred_json:
        firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def run_bot():
    # 2. Telegram Auth
    api_id = int(os.environ.get("API_ID", 0))
    api_hash = os.environ.get("API_HASH", "")
    session_str = os.environ.get("SESSION_STRING", "")
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.start()
    print("🚀 Bot Connected! GitHub High-Speed Mode Active.")

    while True:
        try:
            # ၃။ တန်းစီစနစ် (Queue) - Processing ဟောင်းရှိရင် အရင်ယူ၊ မရှိရင် အစောဆုံး Pending ကိုယူ
            # အရင်ဆုံး processing ဖြစ်နေတာရှိလား စစ်ပါတယ်
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "processing")).limit(1).get()
            
            # မရှိရင် အစောဆုံးတင်ထားတဲ့ pending ကိုယူပါတယ်
            if not tasks:
                tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()

            if not tasks:
                await asyncio.sleep(5); continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            uid = int(data['user_id']); lang = data.get('lang', 'my'); v_url = data['value'].strip()
            last_sent = data.get('last_sent_index', -1)
            
            # Lock Status (Pending ဆိုရင် Processing ပြောင်း)
            if data['status'] == 'pending':
                ref.update({'status': 'processing'})
                ack = "ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပါ။" if lang == 'my' else "Video received. Processing..."
                await client.send_message(uid, ack)

            # ၄။ Download Logic (မူရင်းဖိုင် မရှိမှ ဒေါင်းမည်)
            if not os.path.exists("vid.mp4"):
                print(f"📥 Downloading Original Video for UID: {uid}...")
                if "t.me/" in v_url:
                    p = v_url.split('/')
                    await client.download_media(await client.get_messages(p[-2], ids=int(p[-1])), "vid.mp4")
                else:
                    subprocess.run(['yt-dlp', '--no-check-certificate', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            # ၅။ FFmpeg Processing & Splitting
            os.makedirs("parts", exist_ok=True)
            # အပိုင်းတွေ မခွဲရသေးရင် ဖြတ်ပါမယ်
            if not os.listdir("parts"):
                print("✂️ Splitting Video...")
                duration = sum(x * 60**i for i, x in enumerate(map(int, reversed(data.get('len', '5:00').split(':')))))
                wm_logic = "x='(w-text_w)/2+(w-text_w)/2*sin(t/2)':y='(h-text_h)/2+(h-text_h)/2*sin(t/3)'"
                drawtext = f"drawtext=text='{data.get('wm', '')}':{wm_logic}:fontfile='Pyidaungsu.ttf':fontcolor=white@0.4:fontsize=50"
                
                v_inputs = ['-i', 'vid.mp4']
                if data.get('logo_data'):
                    with open("logo.png", "wb") as f:
                        f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                    v_inputs += ['-i', 'logo.png']
                    pos = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}.get(data['pos'], 'W-w-15:15')
                    f_complex = f"[1:v]scale=150:-1,format=rgba,colorchannelmixer=aa=0.6[l];[0:v]{drawtext}[v1];[v1][l]overlay={pos}"
                    filter_params = ['-filter_complex', f_complex]
                else:
                    filter_params = ['-vf', drawtext]

                ffmpeg_cmd = ['ffmpeg', '-y'] + v_inputs + filter_params + [
                    '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy',
                    '-f', 'segment', '-segment_time', str(duration), '-reset_timestamps', '1', 'parts/p_%03d.mp4'
                ]
                subprocess.run(ffmpeg_cmd, check=True)
                
                # --- [ DISK SPACE SAVER ] ---
                # အပိုင်းခွဲပြီးတာနဲ့ မူရင်းဖိုင်ကြီးကို ချက်ချင်းဖျက်ပါမယ်
                if os.path.exists("vid.mp4"): os.remove("vid.mp4")
                if os.path.exists("logo.png"): os.remove("logo.png")
                print("🗑️ Original file deleted to save space.")

            # ၆။ Smart Upload (မပြီးသေးသည့် အပိုင်းမှ စပို့မည်)
            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            p_label = "အပိုင်း" if lang == 'my' else "Part"
            end_tag = "\n\n(ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else "\n\n(End Part) ✅"
            
            for idx, p in enumerate(files):
                if idx > last_sent:
                    current_part = idx + 1
                    caption = f"🎬 {data.get('name', 'movie')} - {p_label} ({current_part})" if lang == 'my' else f"🎬 {data.get('name', 'movie')} - {p_label} {current_part}"
                    if current_part == len(files): caption += end_tag
                    
                    await client.send_file(uid, f"parts/{p}", caption=caption)
                    ref.update({'last_sent_index': idx})

            # ၇။ Task အောင်မြင်စွာ ပြီးဆုံးခြင်း
            ref.delete()
            # ကျန်ရှိသည့် အပိုင်းဖိုင်များကို ရှင်းလင်းခြင်း
            shutil.rmtree("parts")
            print(f"✅ Finished UID: {uid}. Ready for next task.")

        except Exception as e:
            print(f"🚨 Loop Error: {e}"); await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(run_bot())
