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
    client = TelegramClient(StringSession(os.environ.get("SESSION_STRING")), int(os.environ.get("API_ID")), os.environ.get("API_HASH"))
    await client.start()
    print("🚀 Bot is strictly following the queue (One task at a time).")
    
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
            # ၁။ Processing ဖြစ်နေတဲ့ Task ရှိလား အရင်စစ်မယ် (ရှိရင် အဲ့ဒါကိုပဲ ဆက်လုပ်မယ်)
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "processing")).limit(1).get()
            
            # ၂။ Processing မရှိမှသာ Pending ထဲက အစောဆုံး (createdAt) တစ်ခုကိုပဲ ယူမယ်
            if not tasks:
                tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()

            if not tasks:
                await asyncio.sleep(5)
                continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            uid = int(data.get('user_id', 0))
            lang = data.get('lang', 'my')
            v_url = data.get('value', '').strip()
            
            if not v_url:
                ref.delete(); continue

            # ၃။ Pending Task ဖြစ်နေရင် "လက်ခံရရှိကြောင်း" ပို့ပြီးမှ Status ကို Processing ပြောင်းမယ်
            if data.get('status') == 'pending':
                ack = ("ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။ Split Video များရရှိပါက ပို့ဆောင်ပေးထားပါ့မယ်။\n"
                       "အခြားလုပ်စရာရှိတာများကို စိတ်ချလက်ချ လုပ်ဆောင်ပြီး ဒီဟာကို ပစ်ထားခဲ့ပါ။") if lang == 'my' else \
                      ("Video received! We'll send the split parts once they're ready. Feel free to attend to other tasks.")
                
                await client.send_message(uid, ack, buttons=get_menu(lang))
                ref.update({'status': 'processing'})
                print(f"🔒 Task Locked for {uid}: Processing started...")

            # ၄။ Download Video (မူရင်းဖိုင်ကြီး ဒေါင်းခြင်း)
            if not os.path.exists("vid.mp4"):
                if "t.me/" in v_url:
                    p = v_url.split('/')
                    msg_obj = await client.get_messages(p[-2], ids=int(p[-1]))
                    await client.download_media(msg_obj, "vid.mp4")
                else:
                    subprocess.run(['yt-dlp', '--no-check-certificate', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            # ၅။ Splitting Engine (FFmpeg)
            os.makedirs("parts", exist_ok=True)
            if not os.listdir("parts"):
                split_time = data.get('len') or "5:00"
                dur_parts = list(map(int, reversed(split_time.split(':'))))
                dur_sec = sum(x * 60**i for i, x in enumerate(dur_parts))
                
                wm_text = data.get('wm', '')
                wm_filter = f"drawtext=text='{wm_text}':x='(w-text_w)/2+(w-text_w)/2*sin(t/2)':y='(h-text_h)/2+(h-text_h)/2*sin(t/3)':fontfile='Pyidaungsu.ttf':fontcolor=white@0.4:fontsize=50" if wm_text else "null"
                v_inputs = ['-i', 'vid.mp4']

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

            # ၆။ Smart Upload (Resumable)
            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            last_sent = data.get('last_sent_index', -1)
            p_lbl = "အပိုင်း" if lang == 'my' else "Part"
            
            for idx, p in enumerate(files):
                if idx > last_sent:
                    m_name = data.get('name') or "Movie"
                    caption = f"🎬 {m_name} - {p_lbl} ({idx+1})"
                    if idx + 1 == len(files): caption += ("\n\n(ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else "\n\n(End Part) ✅")
                    
                    await client.send_file(uid, f"parts/{p}", caption=caption, buttons=get_menu(lang))
                    ref.update({'last_sent_index': idx})

            # ၇။ Task အောင်မြင်စွာပြီးဆုံးမှ Database ထဲက ဖျက်မယ်
            ref.delete()
            shutil.rmtree("parts")
            print(f"✅ Finished UID: {uid}. Ready for next task in queue.")

        except Exception as e:
            print(f"🚨 Error: {e}")
            await asyncio.sleep(10) # Error တက်ရင် ခေတ္တနားပြီးမှ ပြန်စစ်မယ်

if __name__ == "__main__":
    asyncio.run(run_bot())
