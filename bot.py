import os, base64, subprocess, asyncio, firebase_admin, json, re
from firebase_admin import credentials, firestore
from telethon import TelegramClient
from telethon.sessions import StringSession
from google.cloud.firestore_v1.base_query import FieldFilter

# 1. Firebase Initialization
if not firebase_admin._apps:
    try:
        cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
        if cred_json:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(cred_json)))
    except Exception as e:
        print(f"Firebase Error: {e}")

db = firestore.client()

async def run_bot():
    # 2. Credentials Setup
    api_id = int(os.environ.get("API_ID"))
    api_hash = os.environ.get("API_HASH")
    session_str = os.environ.get("SESSION_STRING")
    
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.start()
    print("Bot is online and monitoring tasks...")

    while True:
        try:
            # 3. Task Fetching (Pending tasks only)
            tasks = db.collection('tasks').where(
                filter=FieldFilter("status", "==", "pending")
            ).limit(1).get()
            
            if not tasks:
                await asyncio.sleep(5)
                continue
            
            doc = tasks[0]; ref = doc.reference; data = doc.to_dict()
            uid = int(data['user_id']); lang = data.get('lang', 'my')
            v_url = data['value'].strip()
            
            # Status ကို processing လို့ ချက်ချင်းပြောင်းမှ loop မပတ်မှာပါ
            ref.update({'status': 'processing'})
            
            # 4. Instant Feedback
            ack_msg = "သင့် video ကို လက်ခံရရှိပါသည်၊ ဖြတ်ပြီးပါက ပြန်လည်ပို့ဆောင်ပေးပါမည်။" if lang == 'my' else "Video received. Processing now..."
            await client.send_message(uid, ack_msg)

            # 5. Smart Download Logic
            if "t.me/" in v_url:
                parts_url = v_url.split('/')
                peer = parts_url[-2]; msg_id = int(parts_url[-1])
                msg_obj = await client.get_messages(peer, ids=msg_id)
                await client.download_media(msg_obj, "vid.mp4")
            else:
                subprocess.run(['yt-dlp', '--no-check-certificate', '--location', '-f', 'mp4', '-o', 'vid.mp4', v_url], check=True)

            if not os.path.exists("vid.mp4"): raise Exception("Download Failed")

            # 6. Video Processing (Wave Watermark & Logo)
            duration_parts = list(map(int, reversed(data.get('len', '5:00').split(':'))))
            duration_sec = sum(x * 60**i for i, x in enumerate(duration_parts))
            
            # --- [ Pyidaungsu Font အသုံးပြုထားသော Filter ] ---
            # Fontfile path ကို Pyidaungsu.ttf လို့ ပေးထားပါတယ်။
            # x, y logic က စာသားကို wave ပုံစံ တစ်ဗီဒီယိုလုံး ပတ်ရွေ့နေစေမှာပါ။
            logic = "x='(w-text_w)/2 + (w-text_w)/2*sin(t/2)':y='(h-text_h)/2 + (h-text_h)/2*sin(t/3)'"
            drawtext = f"drawtext=text='{data.get('wm', '')}':{logic}:fontfile='Pyidaungsu.ttf':fontcolor=white@0.4:fontsize=50"
            
            v_input = ['-i', 'vid.mp4']
            
            if data.get('logo_data'):
                with open("logo.png", "wb") as f: 
                    f.write(base64.b64decode(data['logo_data'].split(",")[1]))
                v_input = ['-i', 'vid.mp4', '-i', 'logo.png']
                
                pos_map = {"tr": "W-w-15:15", "tl": "15:15", "br": "W-w-15:H-h-15", "bl": "15:H-h-15"}
                pos = pos_map.get(data['pos'], 'W-w-15:15')
                
                # Logo size ကို ညှိပြီး 60% transparent (aa=0.6) လုပ်ပါတယ်။
                full_filter = (
                    f"[1:v]scale=150:-1,format=rgba,colorchannelmixer=aa=0.6[logo];"
                    f"[0:v]{drawtext}[v1];"
                    f"[v1][logo]overlay={pos}"
                )
                filter_cmd = ['-filter_complex', full_filter]
            else:
                filter_cmd = ['-vf', drawtext]

            # 7. Execute FFmpeg Splitting
            os.makedirs("parts", exist_ok=True)
            for f in os.listdir("parts"): os.remove(os.path.join("parts", f))

            cmd = ['ffmpeg', '-y'] + v_input + filter_cmd + [
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                '-c:a', 'copy', '-f', 'segment', '-segment_time', str(duration_sec), 
                '-reset_timestamps', '1', 'parts/p_%03d.mp4'
            ]
            subprocess.run(cmd, check=True)

            # 8. Upload Result (Myanmar/English Adaptive)
            parts_files = sorted([f for f in os.listdir("parts") if f.endswith(".mp4")])
            total_parts = len(parts_files)

            part_label = "အပိုင်း" if lang == 'my' else "Part"
            end_label = "\n\n(ဇာတ်သိမ်းပိုင်း) ✅" if lang == 'my' else "\n\n(End Part) ✅"

            for idx, p in enumerate(parts_files):
                part_num = idx + 1
                # Myanmar: အပိုင်း (၁) | English: Part 1
                caption = f"🎬 {data.get('name', 'movie')} - {part_label} ({part_num})" if lang == 'my' else f"🎬 {data.get('name', 'movie')} - {part_label} {part_num}"
                
                if part_num == total_parts:
                    caption += end_label
                
                await client.send_file(uid, f"parts/{p}", caption=caption)

            # Cleanup
            ref.delete()
            for f in ["vid.mp4", "logo.png"]: 
                if os.path.exists(f): os.remove(f)

        except Exception as e:
            print(f"Error: {e}")
            try: ref.update({'status': 'failed', 'error': str(e)})
            except: pass
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_bot())
