import os, base64, subprocess, asyncio, firebase_admin, json, shutil
from firebase_admin import credentials, firestore
from telethon import TelegramClient, types
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

if not firebase_admin._apps:
    cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if cred_json: firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
db = firestore.client()

async def run_bot():
    client = TelegramClient(StringSession(os.environ.get("SESSION_STRING")), int(os.environ.get("API_ID")), os.environ.get("API_HASH"))
    await client.start()
    
    WEB_URL = os.getenv("WEB_APP_URL", "https://yttott-28862.web.app/")

    def get_menu(lang):
        # app.py နှင့် စာသား ၁၀၀% တူအောင် ပြန်ညှိထားသည်
        opt = {"my": ["🚀 Mini App ဖွင့်ရန်", "👤 My Profile", "💎 Premium ဝယ်ရန်"],
               "en": ["🚀 Open Mini App", "👤 My Profile", "💎 Buy Premium"]}
        l = lang if lang in opt else "my"
        return types.ReplyKeyboardMarkup(rows=[
            types.KeyboardRow(buttons=[types.KeyboardButtonWebApp(text=opt[l][0], url=WEB_URL)]),
            types.KeyboardRow(buttons=[types.KeyboardButton(text=opt[l][1]), types.KeyboardButton(text=opt[l][2])])
        ], resize=True, persistent=True)

    while True:
        try:
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "processing")).limit(1).get()
            if not tasks:
                tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).order_by("createdAt").limit(1).get()

            if not tasks:
                await asyncio.sleep(5); continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            uid, lang, v_url = int(data['user_id']), data.get('lang', 'my'), data['value'].strip()
            last_sent = data.get('last_sent_index', -1)
            
            if data['status'] == 'pending':
                ref.update({'status': 'processing'})
                ack = ("ဗီဒီယို လက်ခံရရှိပါသည် ခဏစောင့်ပေးပါ။ Split Video များရရှိပါက ပို့ဆောင်ပေးထားပါ့မယ်။ "
                       "အခြားလုပ်စရာရှိတာများကို စိတ်ချလက်ချ လုပ်ဆောင်ပြီး ဒီဟာကို ပစ်ထားခဲ့ပါ။") if lang == 'my' else \
                      ("Video received! We'll send the split parts as soon as they're done. "
                       "Feel free to attend to other tasks in the meantime.")
                await client.send_message(uid, ack, buttons=get_menu(lang))

            # Download -> Process -> Split
            if not os.path.exists("vid.mp4"):
                if "t.me/" in v_url:
                    p = v_url.split('/'); await client.download_media(await client.get_messages(p[-2], ids=int(p[-1])), "vid.mp4")
                else: subprocess.run(['yt-dlp', '--no-check-certificate', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            os.makedirs("parts", exist_ok=True)
            if not os.listdir("parts"):
                dur = sum(x * 60**i for i, x in enumerate(map(int, reversed(data.get('len', '5:00').split(':')))))
                wm_logic = "x='(w-text_w)/2+(w-text_w)/2*sin(t/2)':y='(h-text_h)/2+(h-text_h)/2*sin(t/3)'"
                drawtext = f"drawtext=text='{data.get('wm', '')}':{wm_logic}:fontfile='Pyidaungsu.ttf':fontcolor=white@0.4:fontsize=50"
                subprocess.run(['ffmpeg', '-y', '-i', 'vid.mp4', '-vf', drawtext, '-c:v', 'libx264', '-preset', 'veryfast', '-f', 'segment', '-segment_time', str(dur), '-reset_timestamps', '1', 'parts/p_%03d.mp4'], check=True)
                if os.path.exists("vid.mp4"): os.remove("vid.mp4")

            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            p_lbl = "အပိုင်း" if lang == 'my' else "Part"
            for idx, p in enumerate(files):
                if idx > last_sent:
                    cap = f"🎬 {data.get('name')} - {p_lbl} ({idx+1})"
                    if idx + 1 == len(files): cap += ("\n\n(ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else "\n\n(End Part) ✅")
                    await client.send_file(uid, f"parts/{p}", caption=cap, buttons=get_menu(lang))
                    ref.update({'last_sent_index': idx})

            ref.delete(); shutil.rmtree("parts")
        except Exception as e:
            print(f"🚨 Error: {e}"); await asyncio.sleep(5)

if __name__ == "__main__": asyncio.run(run_bot())
