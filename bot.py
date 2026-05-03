import os, base64, subprocess, asyncio, firebase_admin, json, shutil
from firebase_admin import credentials, firestore
from telethon import TelegramClient, types
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# 1. Firebase Initialization
if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if cred_json:
        firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def run_bot():
    # 2. Telegram Auth
    client = TelegramClient(StringSession(os.environ.get("SESSION_STRING")), int(os.environ.get("API_ID")), os.environ.get("API_HASH"))
    await client.start()
    
    WEB_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app/")

    def get_menu(lang):
        opt = {"my": ["🚀 Mini App ဖွင့်ရန်", "👤 My Profile", "💎 Premium ဝယ်ရန်"],
               "en": ["🚀 Open Mini App", "👤 My Profile", "💎 Buy Premium"]}
        l = lang if lang in opt else "my"
        return types.ReplyKeyboardMarkup(rows=[
            types.KeyboardRow(buttons=[types.KeyboardButtonWebApp(text=opt[l][0], url=WEB_URL)]),
            types.KeyboardRow(buttons=[types.KeyboardButton(text=opt[l][1]), types.KeyboardButton(text=opt[l][2])])
        ], resize=True, persistent=True)

    while True:
        try:
            # --- [ RESUME LOGIC ] ---
            # GitHub ပြန်ပွင့်လာရင် Processing ဖြစ်နေတာကို အရင်ရှာတယ်
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "processing")).limit(1).get()
            
            # မရှိမှ Pending ကို အစဉ်လိုက် ထပ်ယူတယ်
            if not tasks:
                tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).order_by("createdAt").limit(1).get()

            if not tasks:
                await asyncio.sleep(5); continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            
            # --- [ Skip & Mandatory Check ] ---
            v_url = data.get('value', '').strip()
            if not v_url:
                ref.delete(); continue

            uid = int(data.get('user_id', 0))
            lang = data.get('lang', 'my')
            m_name = data.get('name') or "Movie Name"
            split_time = data.get('len') or "5:00"
            wm_text = data.get('wm', '')
            last_sent = data.get('last_sent_index', -1) # ဘယ်နှစ်ပိုင်း ပို့ပြီးပြီလဲ မှတ်ထားတဲ့ index
            
            # Status Update
            if data['status'] == 'pending':
                ref.update({'status': 'processing'})
                ack = "ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။" if lang == 'my' else "Video received! Please wait."
                await client.send_message(uid, ack, buttons=get_menu(lang))

            # 4. Download (Disk Saver)
            if not os.path.exists("vid.mp4"):
                if "t.me/" in v_url:
                    p = v_url.split('/'); await client.download_media(await client.get_messages(p[-2], ids=int(p[-1])), "vid.mp4")
                else:
                    subprocess.run(['yt-dlp', '--no-check-certificate', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            # 5. FFmpeg Processing
            os.makedirs("parts", exist_ok=True)
            if not os.listdir("parts"):
                dur_parts = list(map(int, reversed(split_time.split(':'))))
                dur_sec = sum(x * 60**i for i, x in enumerate(dur_parts))
                
                v_inputs = ['-i', 'vid.mp4']
                wm_filter = f"drawtext=text='{wm_text}':x='(w-text_w)/2+(w-text_w)/2*sin(t/2)':y='(h-text_h)/2+(h-text_h)/2*sin(t/3)':fontfile='Pyidaungsu.ttf':fontcolor=white@0.4:fontsize=50" if wm_text else "null"

                if data.get('logo_data'):
                    with open("logo.png", "wb") as f: f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                    v_inputs += ['-i', 'logo.png']
                    pos = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}.get(data.get('pos', 'tr'), "W-w-15:15")
                    f_complex = f"[1:v]scale=150:-1,format=rgba,colorchannelmixer=aa=0.6[l];[0:v]{wm_filter}[v1];[v1][l]overlay={pos}"
                    filter_params = ['-filter_complex', f_complex]
                else:
                    filter_params = ['-vf', wm_filter]

                subprocess.run(['ffmpeg', '-y'] + v_inputs + filter_params + ['-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy', '-f', 'segment', '-segment_time', str(dur_sec), '-reset_timestamps', '1', 'parts/p_%03d.mp4'], check=True)
                
                if os.path.exists("vid.mp4"): os.remove("vid.mp4")
                if os.path.exists("logo.png"): os.remove("logo.png")

            # 6. Smart Resume Upload
            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            p_lbl = "အပိုင်း" if lang == 'my' else "Part"
            
            for idx, p in enumerate(files):
                # အရင်က ပို့ပြီးသား index တွေကို ကျော်မယ်
                if idx > last_sent:
                    caption = f"🎬 {m_name} - {p_lbl} ({idx+1})"
                    if idx + 1 == len(files): caption += "\n\n(ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else "\n\n(End Part) ✅"
                    
                    await client.send_file(uid, f"parts/{p}", caption=caption, buttons=get_menu(lang))
                    # ပို့ပြီးတိုင်း Database မှာ index ကို update လုပ်တယ်
                    ref.update({'last_sent_index': idx})

            # 7. Final Success
            ref.delete()
            shutil.rmtree("parts")
            print(f"✅ Job Completed for {uid}")

        except Exception as e:
            print(f"🚨 Error: {e}"); await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_bot())
