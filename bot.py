import os, json, asyncio, subprocess, firebase_admin, gdown
from firebase_admin import credentials, firestore
from pyrogram import Client

cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT')))
if not firebase_admin._apps: firebase_admin.initialize_app(cred)
db = firestore.client()

async def main():
    async with Client("bot_proc", int(os.environ.get("API_ID")), os.environ.get("API_HASH"), bot_token=os.environ.get("TELEGRAM_TOKEN")) as app:
        while True:
            query = db.collection('tasks').where(filter=firestore.FieldFilter("status", "==", "pending")).order_by("createdAt").limit(1).get()
            if not query: break
            doc = query[0]; data = doc.to_dict(); doc.reference.update({'status': 'processing'})
            try:
                target = "movie.mp4"
                if data['type'] == 'video': await app.download_media(data['value'], file_name=target)
                else:
                    if 'drive.google.com' in data['value']: gdown.download(data['value'], target, quiet=False, fuzzy=True)
                    else: subprocess.run(f'yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" "{data["value"]}" -o {target}', shell=True)
                
                # Split & Watermark
                subprocess.run(f'ffmpeg -i {target} -c copy -f segment -segment_time {int(data["len"])*60} -reset_timestamps 1 "p_%d.mp4"', shell=True)
                parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(x.split('_')[1].split('.')[0]))
                
                for i, p in enumerate(parts):
                    out = f"out_{i}.mp4"
                    vf = f"drawtext=text='{data['wm']}':fontcolor=white:fontsize=h/20:x=10:y=10" if data['wm'] else "null"
                    subprocess.run(f'ffmpeg -y -i "{p}" -vf "{vf}" -c:v libx264 -crf 23 -c:a copy {out}', shell=True)
                    await app.send_video(data['user_id'], video=out, caption=f"{data['name']} Part {i+1}"); os.remove(p); os.remove(out)
                
                os.remove(target); doc.reference.update({'status': 'completed'})
            except Exception as e: doc.reference.update({'status': 'error', 'error_msg': str(e)})

if __name__ == "__main__": asyncio.run(main())
