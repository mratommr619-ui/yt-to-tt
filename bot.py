import os, base64, subprocess, asyncio, firebase_admin, json, re, shutil
from firebase_admin import credentials, firestore
from telethon import TelegramClient, events, types
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
    print("🚀 Bot Connected! Sequential Resumable Mode with Menu Fix.")

    # --- [ Menu Keyboard Logic ] ---
    # app.py မှာသုံးထားတဲ့ Menu တွေကို ပျောက်မသွားအောင် ပြန်ပေါ်စေမယ့် function
    def get_menu_keyboard(lang):
        open_text = "🚀 Mini App ဖွင့်ရန်" if lang == 'my' else "🚀 Open Mini App"
        profile_text = "👤 My Profile" if lang == 'my' else "👤 My Profile"
        buy_text = "💎 Premium ဝယ်ရန်" if lang == 'my' else "💎 Buy Premium"
        
        # Telethon style ReplyMarkup (app.py ထဲက Keyboard နဲ့ တစ်ထပ်တည်း)
        return types.ReplyKeyboardMarkup(
            rows=[
                types.KeyboardRow(buttons=[types.KeyboardButton(text=open_text)]),
                types.KeyboardRow(buttons=[
                    types.KeyboardButton(text=profile_text),
                    types.KeyboardButton(text=buy_text)
                ])
            ],
            resize=True
        )

    while True:
        try:
            # 3. Queue Logic
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "processing")).limit(1).get()
            if not tasks:
                tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).order_by("createdAt", direction=firestore.Query.ASCENDING).limit(1).get()

            if not tasks:
                await asyncio.sleep(5); continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            uid = int(data['user_id']); lang = data.get('lang', 'my'); v_url = data['value'].strip()
            last_sent = data.get('last_sent_index', -1)
            
            # Status Update
            if data['status'] == 'pending':
                ref.update({'status': 'processing'})
                ack = "သင့် video ကို လက်ခံရရှိပါသည်၊ ဖြတ်ပြီးပါက ပြန်လည်ပို့ဆောင်ပေးပါမည်။" if lang == 'my' else "Video received. Processing now..."
                # စာပို့တဲ့အချိန်မှာ Menu Keyboard ကိုပါ တွဲပို့ပေးခြင်းဖြင့် ပျောက်မသွားအောင်လုပ်သည်
                await client.send_message(uid, ack, buttons=get_menu_keyboard(lang))

            # 4. Download (Disk Space Saver logic)
            if not os.path.exists("vid.mp4"):
                if "t.me/" in v_url:
                    p = v_url.split('/')
                    await client.download_media(await client.get_messages(p[-2], ids=int(p[-1])), "vid.mp4")
                else:
                    subprocess.run(['yt-dlp', '--no-check-certificate', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            # 5. FFmpeg (Wave Watermark 50px + 60% Alpha Logo)
            os.makedirs("parts", exist_ok=True)
            if not os.listdir("parts"):
                dur = sum(x * 60**i for i, x in enumerate(map(int, reversed(data.get('len', '5:00').split(':')))))
                wm_logic = "x='(w-text_w)/2+(w-text_w)/2*sin(t/2)':y='(h-text_h)/2+(h-text_h)/2*sin(t/3)'"
                drawtext = f"drawtext=text='{data.get('wm', '')}':{wm_logic}:fontfile='Pyidaungsu.ttf':fontcolor=white@0.4:fontsize=50"
                
                v_inputs = ['-i', 'vid.mp4']
                if data.get('logo_data'):
                    with open("logo.png", "wb") as f: f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                    v_inputs += ['-i', 'logo.png']
                    pos = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}.get(data['pos'], 'W-w-15:15')
                    f_comp = f"[1:v]scale=150:-1,format=rgba,colorchannelmixer=aa=0.6[l];[0:v]{drawtext}[v1];[v1][l]overlay={pos}"
                    filter_params = ['-filter_complex', f_comp]
                else:
                    filter_params = ['-vf', drawtext]

                subprocess.run(['ffmpeg', '-y'] + v_inputs + filter_params + ['-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'copy', '-f', 'segment', '-segment_time', str(dur), '-reset_timestamps', '1', 'parts/p_%03d.mp4'], check=True)
                
                # Disk Space Saver (ဖိုင်ခွဲပြီးတာနဲ့ မူရင်းဖိုင်ဖျက်)
                if os.path.exists("vid.mp4"): os.remove("vid.mp4")

            # 6. Upload with Persistent Menu
            files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            p_label = "အပိုင်း" if lang == 'my' else "Part"
            end_tag = "\n\n(ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else "\n\n(End Part) ✅"
            
            for idx, p in enumerate(files):
                if idx > last_sent:
                    part_num = idx + 1
                    caption = f"🎬 {data.get('name', 'movie')} - {p_label} ({part_num})" if lang == 'my' else f"🎬 {data.get('name', 'movie')} - {p_label} {part_num}"
                    if part_num == len(files): caption += end_tag
                    
                    # ဗီဒီယိုပို့တိုင်း Menu Keyboard ပါ ပါအောင်လုပ်ခြင်းဖြင့် User ခလုတ်တွေ ပျောက်မသွားတော့ပါ
                    await client.send_file(uid, f"parts/{p}", caption=caption, buttons=get_menu_keyboard(lang))
                    ref.update({'last_sent_index': idx})

            # 7. Cleanup
            ref.delete()
            shutil.rmtree("parts")
            if os.path.exists("logo.png"): os.remove("logo.png")

        except Exception as e:
            print(f"🚨 Error: {e}"); await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(run_bot())
