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
        # Telegram Client Setup
        client = TelegramClient(StringSession(os.environ.get("SESSION_STRING")), int(os.environ.get("API_ID")), os.environ.get("API_HASH"))
        await client.start()
        print("🚀 Bot Connected! Full logic restored and running...")
        
        WEB_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app/")

        def get_menu(lang):
            # စာသားများကို app.py နှင့် တိကျစွာ ညှိထားပါသည်
            opt = {
                "my": ["🚀 Mini App ဖွင့်ရန်", "👤 My Profile", "💎 Premium ဝယ်ရန်"],
                "en": ["🚀 Open Mini App", "👤 My Profile", "💎 Buy Premium"]
            }
            l = lang if lang in opt else "my"
            return types.ReplyKeyboardMarkup(rows=[
                types.KeyboardRow(buttons=[types.KeyboardButtonWebApp(text=opt[l][0], url=WEB_URL)]),
                types.KeyboardRow(buttons=[
                    types.KeyboardButton(text=opt[l][1]), 
                    types.KeyboardButton(text=opt[l][2])
                ])
            ], resize=True, persistent=True)

        # --- [ Background Task: Acknowledgement ] ---
        # ဒီ loop က main worker နဲ့ မဆိုင်ဘဲ pending ရှိတာနဲ့ စာလှမ်းပို့ပေးနေမှာပါ
        async def ack_handler():
            while True:
                try:
                    pendings = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).get()
                    for p in pendings:
                        p_data = p.to_dict()
                        uid = int(p_data.get('user_id', 0))
                        lang = p_data.get('lang', 'my')
                        
                        ack = ("ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။ Split Video များရရှိပါက ပို့ဆောင်ပေးထားပါ့မယ်။\n"
                               "အခြားလုပ်စရာရှိတာများကို စိတ်ချလက်ချ လုပ်ဆောင်ပြီး ဒီဟာကို ပစ်ထားခဲ့ပါ။") if lang == 'my' else \
                              ("Video received! Please wait. Your split videos will be sent once ready.")
                        
                        try:
                            await client.send_message(uid, ack, buttons=get_menu(lang))
                            # စာပို့ပြီးတာနဲ့ Queue ထဲမှာ တန်းစီခိုင်းလိုက်မယ်
                            p.reference.update({'status': 'queued'})
                            print(f"📩 Sent Ack to {uid}")
                        except: pass
                    await asyncio.sleep(5)
                except: await asyncio.sleep(10)

        asyncio.create_task(ack_handler())

        # --- [ Main Task: Worker Engine ] ---
        while True:
            try:
                # ၁။ Processing ဖြစ်နေတာရှိရင် အရင်ကိုင် (Restart ဖြစ်ရင် ဆက်လုပ်နိုင်ရန်)
                tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "processing")).limit(1).get()
                
                # ၂။ မရှိရင် queued (စာပို့ပြီးသား) ထဲက အဟောင်းဆုံးကို ယူ
                if not tasks:
                    tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "queued")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()

                if not tasks:
                    await asyncio.sleep(10); continue
                
                doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
                uid = int(data.get('user_id', 0))
                lang = data.get('lang', 'my')
                v_url = data.get('value', '').strip()
                
                if not v_url:
                    ref.delete(); continue

                # Status Lock
                if data['status'] == 'queued':
                    ref.update({'status': 'processing'})

                # --- [ Parameters & Defaults ] ---
                m_name = data.get('name') or "Movie Name"
                split_time = data.get('len') or "5:00"
                wm_text = data.get('wm', '')
                last_sent = data.get('last_sent_index', -1)

                # --- [ Download ] ---
                if not os.path.exists("vid.mp4"):
                    if "t.me/" in v_url:
                        p = v_url.split('/'); msg_obj = await client.get_messages(p[-2], ids=int(p[-1]))
                        await client.download_media(msg_obj, "vid.mp4")
                    else:
                        subprocess.run(['yt-dlp', '--no-check-certificate', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

                # --- [ FFmpeg Processing ] ---
                os.makedirs("parts", exist_ok=True)
                if not os.listdir("parts"):
                    dur_sec = sum(x * 60**i for i, x in enumerate(map(int, reversed(split_time.split(':')))))
                    
                    v_inputs = ['-i', 'vid.mp4']
                    wm_logic = "x='(w-text_w)/2+(w-text_w)/2*sin(t/2)':y='(h-text_h)/2+(h-text_h)/2*sin(t/3)'"
                    drawtext = f"drawtext=text='{wm_text}':{wm_logic}:fontfile='Pyidaungsu.ttf':fontcolor=white@0.4:fontsize=50" if wm_text else "null"

                    if data.get('logo_data'):
                        with open("logo.png", "wb") as f:
                            f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                        v_inputs += ['-i', 'logo.png']
                        pos = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}.get(data.get('pos', 'tr'), "W-w-15:15")
                        # Logo Size 150px & 60% Transparency (aa=0.6)
                        f_complex = f"[1:v]scale=150:-1,format=rgba,colorchannelmixer=aa=0.6[l];[0:v]{drawtext}[v1];[v1][l]overlay={pos}"
                        filter_params = ['-filter_complex', f_complex]
                    else:
                        filter_params = ['-vf', drawtext]

                    subprocess.run(['ffmpeg', '-y'] + v_inputs + filter_params + [
                        '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy',
                        '-f', 'segment', '-segment_time', str(dur_sec), '-reset_timestamps', '1', 'parts/p_%03d.mp4'
                    ], check=True)
                    
                    if os.path.exists("vid.mp4"): os.remove("vid.mp4")
                    if os.path.exists("logo.png"): os.remove("logo.png")

                # --- [ Smart Upload (Resumable) ] ---
                files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
                for idx, p in enumerate(files):
                    if idx > last_sent:
                        p_lbl = "အပိုင်း" if lang == 'my' else "Part"
                        caption = f"🎬 {m_name} - {p_lbl} ({idx+1})"
                        if idx + 1 == len(files):
                            caption += "\n\n(ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else "\n\n(End Part) ✅"
                        
                        await client.send_file(uid, f"parts/{p}", caption=caption, buttons=get_menu(lang))
                        ref.update({'last_sent_index': idx})

                # --- [ Success Cleanup ] ---
                ref.delete()
                shutil.rmtree("parts")
                print(f"✅ Job Finished for User {uid}")

            except Exception as e:
                print(f"🚨 Worker Error: {e}"); await asyncio.sleep(10)
    except Exception as e:
        print(f"🚨 Bot Crash: {e}"); await asyncio.sleep(20)

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(run_bot())
        except:
            time.sleep(10)
