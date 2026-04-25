import os, json, asyncio, subprocess, firebase_admin, re
from firebase_admin import credentials, firestore
from pyrogram import Client
import gdown

# --- Setup ---
API_ID = int(os.environ.get('API_ID'))
API_HASH = os.environ.get('API_HASH')
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')

cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT')))
if not firebase_admin._apps: firebase_admin.initialize_app(cred)
db = firestore.client()

async def main():
    query = db.collection('tasks').where('status', '==', 'pending').order_by('createdAt').limit(1).get()
    if not query: return
    doc = query[0]
    data = doc.to_dict()
    doc.reference.update({'status': 'processing'})

    async with Client("bot_session", API_ID, API_HASH, bot_token=BOT_TOKEN) as app:
        try:
            print("Download started...")
            if data['type'] == 'video':
                # Pyrogram download (Up to 2GB/4GB)
                path = await app.download_media(data['value'], file_name="movie.mp4")
            else:
                url = data['value']
                # Google Drive Check
                if 'drive.google.com' in url:
                    gdown.download(url, "movie.mp4", quiet=False, fuzzy=True)
                else:
                    # yt-dlp (YT, Bilibili, FB, TikTok, etc)
                    cmd = f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" "{url}" -o movie.mp4'
                    subprocess.run(cmd, shell=True)
            
            if not os.path.exists("movie.mp4"): raise Exception("Download Failed")

            # Split
            split_sec = data['len'] * 60
            subprocess.run(f'ffmpeg -i movie.mp4 -c copy -f segment -segment_time {split_sec} -reset_timestamps 1 "p_%d.mp4"', shell=True)
            
            parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(x.split('_')[1].split('.')[0]))
            await app.send_message(data['user_id'], f"✅ အပိုင်း ({len(parts)}) ပိုင်း ရရှိပါသည်။ အစဉ်အတိုင်း ပို့ပေးနေပါပြီ...")

            for i, p in enumerate(parts):
                label = f"Part {i+1}"
                caption = f"{data['name']} + {label} {data['wm']}"
                vf = f"drawtext=text='{label}':fontcolor=white:fontsize=h/10:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
                
                # Encode with watermark and label
                subprocess.run(f'ffmpeg -y -i "{p}" -vf "{vf}" -c:v libx264 -crf 23 -c:a copy "out.mp4"', shell=True)
                await app.send_video(data['user_id'], video="out.mp4", caption=caption)
                os.remove(p); os.remove("out.mp4")

            os.remove("movie.mp4")
            doc.reference.update({'status': 'completed'})
        except Exception as e:
            doc.reference.update({'status': 'error', 'error_msg': str(e)})

if __name__ == "__main__": asyncio.run(main())
