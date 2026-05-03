import os, base64, subprocess, asyncio, firebase_admin, json, re
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# 1. Firebase Configuration & Initialization
# Firebase Account JSON ကို Environment variable ကနေယူပြီး initialize လုပ်ပါတယ်။
if not firebase_admin._apps:
    try:
        cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            # JSON string ကို dictionary အဖြစ် parse လုပ်ပါတယ်။
            cred_dict = json.loads(cred_json)
            firebase_admin.initialize_app(credentials.Certificate(cred_dict))
    except Exception as e:
        print(f"Firebase Init Error: {e}")

db = firestore.client()

async def run_bot():
    # 2. Security Setup & Telegram Client Connection
    # Sensitive data တွေကို environment variable ကနေပဲ သုံးပါတယ်။
    try:
        api_id = int(os.environ.get("API_ID"))
        api_hash = os.environ.get("API_HASH")
        session_str = os.environ.get("SESSION_STRING")
        
        client = TelegramClient(StringSession(session_str), api_id, api_hash)
        await client.start()
        print("Bot is online and waiting for tasks...")
    except Exception as e:
        print(f"Telegram Connection Error: {e}")
        return

    while True:
        try:
            # 3. Task Listening (Firestore ထဲမှ pending ဖြစ်နေသော task ကို တစ်ခုချင်းယူပါတယ်)
            tasks = db.collection('tasks').where(filter=FieldFilter("status", "==", "pending")).limit(1).get()
            
            if not tasks:
                await asyncio.sleep(5)
                continue
            
            doc = tasks[0]; data = doc.to_dict(); ref = doc.reference
            uid = int(data['user_id']); lang = data.get('lang', 'my')
            v_url = data['value'].strip()
            
            # 4. Instant Feedback (User ကို အလုပ်စနေကြောင်း အသိပေးပါတယ်)
            ack_msg = "သင့် video ကို လက်ခံရရှိပါသည်၊ ဖြတ်ပြီးပါက ပြန်လည်ပို့ဆောင်ပေးပါမည်။" if lang == 'my' else "Video received. Will send back once split is done."
            await client.send_message(uid, ack_msg)
            
            # Status ကို processing သို့ ပြောင်းပါတယ်
            ref.update({'status': 'processing'})

            # 5. Smart Download Logic (Link အမျိုးအစားအလိုက် downloader ခွဲသုံးပါတယ်)
            print(f"Downloading: {v_url}")
            if "t.me/" in v_url:
                # Telegram link အတွက် Telethon သုံးပါတယ်
                parts = v_url.split('/')
                # peer (channel/group username or ID) နှင့် message ID ကို ခွဲထုတ်ပါတယ်
                peer = parts[-2]
                msg_id = int(parts[-1])
                msg_obj = await client.get_messages(peer, ids=msg_id)
                await client.download_media(msg_obj, "vid.mp4")
            else:
                # အခြား link များအတွက် yt-dlp ကို သုံးပါတယ်
                subprocess.run(['yt-dlp', '--no-check-certificate', '--location', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            if not os.path.exists("vid.mp4"): 
                raise Exception("Download Failed")

            # 6. Video Processing with Myanmar Font & Overlay
            # '5:00' ကဲ့သို့သော string ကို total seconds အဖြစ် ပြောင်းပါတယ်
            duration_parts = list(map(int, reversed(data.get('len', '5:00').split(':'))))
            duration_sec = sum(x * 60**i for i, x in enumerate(duration_parts))
            
            filters = []
            
            # Watermark (Moving text logic)
            if data.get('wm'):
                wm_text = data['wm']
                # Watermark ကို screen အနှံ့ ရွေ့လျားနေစေမည့် FFmpeg logic
                logic = "x='if(lt(mod(t,10),5),w*0.1,w*0.7)':y='if(lt(mod(t,6),3),h*0.1,h*0.8)'"
                # Project folder ထဲတွင် Pyidaungsu.ttf ရှိနေရန် လိုအပ်သည်
                filters.append(f"drawtext=text='{wm_text}':{logic}:fontfile='Pyidaungsu.ttf':fontcolor=white@0.5:fontsize=30")
            
            v_input = ['-i', 'vid.mp4']
            
            # Logo Overlay (Base64 မှ logo.png အဖြစ် ပြောင်းပါတယ်)
            if data.get('logo_data'):
                with open("logo.png", "wb") as f: 
                    # data:image/png;base64, အစရှိသော header ကို ဖယ်ထုတ်ပါတယ်
                    f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                v_input = ['-i', 'vid.mp4', '-i', 'logo.png']
                # Corner position map
                pos_map = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}
                filters.append(f"[0:v][1:v]overlay={pos_map.get(data['pos'], 'W-w-15:15')}")

            # Splitting Process (ဗီဒီယိုကို အပိုင်းဖြတ်ပါတယ်)
            os.makedirs("parts", exist_ok=True)
            for f in os.listdir("parts"): os.remove(os.path.join("parts", f)) # folder ရှင်းလင်းရေး

            print("Starting FFmpeg Splitting...")
            ffmpeg_cmd = ['ffmpeg', '-y'] + v_input + [
                '-vf', ",".join(filters) if filters else "copy", 
                '-f', 'segment', '-segment_time', str(duration_sec), 
                '-reset_timestamps', '1', 'parts/p_%03d.mp4'
            ]
            subprocess.run(ffmpeg_cmd, check=True)

            # 7. Sending Results (ရလဒ်များကို ပြန်ပို့ပါတယ်)
            # အပိုင်းများကို နာမည်အလိုက် စနစ်တကျ စီပါတယ်
            parts = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")], key=lambda x: int(re.findall(r'\d+', x)[0]))
            
            for idx, p in enumerate(parts):
                caption = f"🎬 {data.get('name', 'movie')} - Part {idx+1}"
                # နောက်ဆုံးအပိုင်းတွင် 'ဇာတ်သိမ်းပိုင်း' ဟု caption ထည့်ပါတယ်
                if idx + 1 == len(parts):
                    caption += " (ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else " (End Part) ✅"
                
                await client.send_file(uid, f"parts/{p}", caption=caption)
                ref.update({'last_sent_index': idx})

            # Cleanup: database ထဲမှ task ကိုဖျက်ပြီး ယာယီဖိုင်များကို ရှင်းလင်းပါတယ်
            ref.delete()
            for f in ["vid.mp4", "logo.png"]: 
                if os.path.exists(f): os.remove(f)
            print("Task Completed Successfully.")

        except Exception as e:
            print(f"Error occurred: {e}")
            # Error ဖြစ်ပါက Retrying လုပ်နိုင်ရန် status ကို pending ပြန်ပို့ပါတယ်
            try: ref.update({'status': 'pending'})
            except: pass
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_bot())
