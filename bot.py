import os, base64, subprocess, asyncio, firebase_admin, json, shutil, time
from firebase_admin import credentials, firestore
from telethon import TelegramClient, types
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# 1. Firebase Initializer
if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if cred_json:
        firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def run_bot():
    try:
        client = TelegramClient(StringSession(os.environ.get("SESSION_STRING")), int(os.environ.get("API_ID")), os.environ.get("API_HASH"))
        await client.start()
        print("🚀 Bot Connected! Persistent Queue Engine Active.")
        
        WEB_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app/")

        def get_menu(lang):
            opt = {"my": ["🚀 Mini App ဖွင့်ရန်", "👤 My Profile", "💎 Premium ဝယ်ရန်"],
                   "en": ["🚀 Open Mini App", "👤 My Profile", "💎 Buy Premium"]}
            l = lang if lang in opt else "my"
            return types.ReplyKeyboardMarkup(rows=[
                types.KeyboardRow(buttons=[types.KeyboardButtonWebApp(text=opt[l][0], url=WEB_URL)]),
                types.KeyboardRow(buttons=[types.KeyboardButton(text=opt[l][1]), types.KeyboardButton(text=opt[l][2])])
            ], resize=True, persistent=True)

        # --- [ Background Task: Acknowledgement ] ---
        async def ack_handler():
            while True:
                try:
                    # Pending တွေ့တာနဲ့ စာပို့ပြီး queued ပြောင်းမယ်
                    pendings = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).get()
                    for p in pendings:
                        p_data = p.to_dict()
                        uid, lang = int(p_data.get('user_id', 0)), p_data.get('lang', 'my')
                        
                        ack = ("ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။ Split Video များရရှိပါက ပို့ဆောင်ပေးထားပါ့မယ်။\n"
                               "အခြားလုပ်စရာရှိတာများကို စိတ်ချလက်ချ လုပ်ဆောင်ပြီး ဒီဟာကို ပစ်ထားခဲ့ပါ။") if lang == 'my' else \
                              ("Video received! Please wait. Your split videos will be sent once ready.")
                        
                        await client.send_message(uid, ack, buttons=get_menu(lang))
                        p.reference.update({'status': 'queued'})
                        print(f"📩 Sent Ack & Marked Queued for {uid}")
                    await asyncio.sleep(3)
                except Exception as e:
                    print(f"Ack Error: {e}"); await asyncio.sleep(5)

        asyncio.create_task(ack_handler())

        # --- [ Main Task: Worker ] ---
        while True:
            try:
                # ၁။ Processing ကို အရင်ကြည့်မယ်
                tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "processing")).limit(1).get()
                
                # ၂။ မရှိရင် queued ထဲက အဟောင်းဆုံးကို ယူမယ်
                if not tasks:
                    tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "queued")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()

                if not tasks:
                    await asyncio.sleep(5); continue
                
                doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
                uid, lang, v_url = int(data.get('user_id', 0)), data.get('lang', 'my'), data.get('value', '').strip()
                
                if not v_url:
                    ref.delete(); continue

                if data['status'] == 'queued':
                    ref.update({'status': 'processing'})

                # --- [ Download & Splitting Logic (Original Specs) ] ---
                if not os.path.exists("vid.mp4"):
                    if "t.me/" in v_url:
                        p = v_url.split('/'); msg_obj = await client.get_messages(p[-2], ids=int(p[-1]))
                        await client.download_media(msg_obj, "vid.mp4")
                    else:
                        subprocess.run(['yt-dlp', '--no-check-certificate', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True, timeout=600)

                os.makedirs("parts", exist_ok=True)
                if not os.listdir("parts"):
                    split_time = data.get('len') or "5:00"
                    dur_sec = sum(x * 60**i for i, x in enumerate(map(int, reversed(split_time.split(':')))))
                    wm_text = data.get('wm', '')
                    drawtext = f"drawtext=text='{wm_text}':x='(w-text_w)/2+(w-text_w)/2*sin(t/2)':y='(h-text_h)/2+(h-text_h)/2*sin(t/3)':fontfile='Pyidaungsu.ttf':fontcolor=white@0.4:fontsize=50" if wm_text else "null"
                    
                    v_in = ['-i', 'vid.mp4']
                    if data.get('logo_data'):
                        with open("logo.png", "wb") as f: f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                        v_in += ['-i', 'logo.png']
                        pos = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}.get(data.get('pos', 'tr'), "W-w-15:15")
                        f_comp = f"[1:v]scale=150:-1,format=rgba,colorchannelmixer=aa=0.6[l];[0:v]{drawtext}[v1];[v1][l]overlay={pos}"
                        filter_p = ['-filter_complex', f_comp]
                    else:
                        filter_p = ['-vf', drawtext]

                    subprocess.run(['ffmpeg', '-y'] + v_in + filter_p + ['-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy', '-f', 'segment', '-segment_time', str(dur_sec), '-reset_timestamps', '1', 'parts/p_%03d.mp4'], check=True)
                    if os.path.exists("vid.mp4"): os.remove("vid.mp4")
                    if os.path.exists("logo.png"): os.remove("logo.png")

                # --- [ Delivery with Resumable Support ] ---
                files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
                last_sent = data.get('last_sent_index', -1)
                for idx, p in enumerate(files):
                    if idx > last_sent:
                        m_name = data.get('name') or "Movie"
                        p_lbl = "အပိုင်း" if lang == 'my' else "Part"
                        cap = f"🎬 {m_name} - {p_lbl} ({idx+1})"
                        if idx + 1 == len(files): cap += "\n\n(ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else "\n\n(End Part) ✅"
                        await client.send_file(uid, f"parts/{p}", caption=cap, buttons=get_menu(lang))
                        ref.update({'last_sent_index': idx})

                ref.delete()
                shutil.rmtree("parts")

            except Exception as e:
                print(f"🚨 Worker Error: {e}"); await asyncio.sleep(10)
    except Exception as e:
        print(f"🚨 Critical Bot Crash: {e}"); await asyncio.sleep(20)

if __name__ == "__main__":
    while True:
        try: asyncio.run(run_bot())
        except: time.sleep(10)
