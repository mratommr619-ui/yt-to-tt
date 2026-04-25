import os, json, asyncio, subprocess, firebase_admin, gdown
from firebase_admin import credentials, firestore
from pyrogram import Client

# --- Setup ---
API_ID = int(os.environ.get('API_ID'))
API_HASH = os.environ.get('API_HASH')
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')

cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT')))
if not firebase_admin._apps: firebase_admin.initialize_app(cred)
db = firestore.client()

async def main():
    tasks_ref = db.collection('tasks')
    query = tasks_ref.where(filter=firestore.FieldFilter("status", "==", "pending")).order_by("createdAt").limit(1).get()
    
    if not query: return
    doc = query[0]
    data = doc.to_dict()
    uid, lang = data['user_id'], data.get('lang', 'my')
    doc.reference.update({'status': 'processing'})

    async with Client("bot_proc", API_ID, API_HASH, bot_token=BOT_TOKEN) as app:
        try:
            if data['type'] == 'video':
                path = await app.download_media(data['value'], file_name="movie.mp4")
            else:
                url = data['value']
                if 'drive.google.com' in url:
                    gdown.download(url, "movie.mp4", quiet=False, fuzzy=True)
                else:
                    subprocess.run(f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" "{url}" -o movie.mp4', shell=True)
            
            if not os.path.exists("movie.mp4"): raise Exception("Download Failed")

            split_sec = int(data['len']) * 60
            subprocess.run(f'ffmpeg -i movie.mp4 -c copy -f segment -segment_time {split_sec} -reset_timestamps 1 "p_%d.mp4"', shell=True)
            parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(x.split('_')[1].split('.')[0]))
            
            p_txt = f"✅ အပိုင်း ({len(parts)}) ပိုင်း ရရှိပါသည်။ ပို့ပေးနေပါပြီ..." if lang == 'my' else f"✅ ({len(parts)}) parts ready. Sending..."
            await app.send_message(uid, p_txt)

            for i, p in enumerate(parts):
                is_last = (i == len(parts) - 1)
                if lang == 'my':
                    label = f"အပိုင်း({i+1})" if not is_last else "ဇာတ်သိမ်းပိုင်း"
                else:
                    label = f"Part-{i+1}" if not is_last else "End Part"
                
                caption = f"{data['name']} + {label} {data['wm']}"
                vf = f"drawtext=text='{label}':fontcolor=white:fontsize=h/10:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
                
                subprocess.run(f'ffmpeg -y -i "{p}" -vf "{vf}" -c:v libx264 -crf 23 -c:a copy "out.mp4"', shell=True)
                await app.send_video(uid, video="out.mp4", caption=caption)
                os.remove(p); os.remove("out.mp4")

            os.remove("movie.mp4")
            doc.reference.update({'status': 'completed'})
        except Exception as e:
            doc.reference.update({'status': 'error', 'error_msg': str(e)})

if __name__ == "__main__": asyncio.run(main())
