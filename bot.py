import os
import json
import asyncio
import subprocess
import firebase_admin
from firebase_admin import credentials, firestore
from pyrogram import Client

# --- Setup ---
API_ID = int(os.environ.get('API_ID'))
API_HASH = os.environ.get('API_HASH')
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')

cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(cert_dict)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

async def main():
    query = db.collection('tasks').where('status', '==', 'pending').order_by('createdAt').limit(1).get()
    if not query: return

    task_doc = query[0]
    data = task_doc.to_dict()
    user_id, lang = data.get('user_id'), data.get('lang', 'my')
    movie_name, wm_text = data.get('movieName'), data.get('watermark')
    split_time = int(data.get('split_minute', 5)) * 60

    task_doc.reference.update({'status': 'processing'})

    async with Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN) as app:
        try:
            # Download Video (No 20MB limit)
            print("Downloading...")
            file_path = await app.download_media(data['file_id'], file_name="movie.mp4")
            
            # Split
            subprocess.run(f'ffmpeg -i "movie.mp4" -c copy -f segment -segment_time {split_time} -reset_timestamps 1 "p_%d.mp4"', shell=True)
            parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(x.split('_')[1].split('.')[0]))
            num_parts = len(parts)

            # Send Status
            status_txt = f"✅ ဗီဒီယိုကို အပိုင်း ({num_parts}) ပိုင်း ရရှိပါသည်။ အစဉ်အတိုင်း ပို့ဆောင်ပေးသွားပါမည်။" if lang == 'my' else f"✅ Video split into ({num_parts}) parts. Sending..."
            await app.send_message(user_id, status_txt)

            for i, p in enumerate(parts):
                is_last = (i == num_parts - 1)
                label = (f"အပိုင်း({i+1})" if lang == 'my' else f"Part-{i+1}") if not is_last else ("ဇာတ်သိမ်းပိုင်း" if lang == 'my' else "End Part")
                
                caption = f"{movie_name} + {label}"
                if wm_text: caption += f" + {wm_text}"

                vf = f"drawtext=text='{label}':fontcolor=white:fontsize=h/10:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
                if wm_text: vf += f",drawtext=text='{wm_text}':fontcolor=white@0.3:fontsize=h/22:x=w-text_w-20:y=h-text_h-20"
                
                subprocess.run(f'ffmpeg -y -i "{p}" -vf "{vf}" -c:v libx264 -crf 20 -c:a copy "out.mp4"', shell=True)
                await app.send_video(user_id, video="out.mp4", caption=caption)
                
                os.remove(p)
                os.remove("out.mp4")

            os.remove("movie.mp4")
            task_doc.reference.update({'status': 'completed'})
        except Exception as e:
            task_doc.reference.update({'status': 'error', 'error_msg': str(e)})

if __name__ == "__main__":
    asyncio.run(main())
