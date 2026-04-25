import os
import json
import subprocess
import requests
import firebase_admin
from firebase_admin import credentials, firestore

try:
    cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(cert_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except: exit(1)

TOKEN = os.environ.get('TELEGRAM_TOKEN')

def process():
    query = db.collection('tasks').where('status', '==', 'pending').order_by('createdAt').limit(1).get()
    if not query: return

    task_doc = query[0]
    data = task_doc.to_dict()
    user_id, lang = data.get('user_id'), data.get('lang', 'my')
    movie_name, wm_text = data.get('movieName'), data.get('watermark')
    split_time = int(data.get('split_minute', 5)) * 60

    task_doc.reference.update({'status': 'processing'})
    res = requests.get(f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={data['file_id']}").json()
    video_url = f"https://api.telegram.org/file/bot{TOKEN}/{res['result']['file_path']}"

    with requests.get(video_url, stream=True) as r:
        with open("movie.mp4", 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)

    try:
        subprocess.run(f'ffmpeg -i "movie.mp4" -c copy -f segment -segment_time {split_time} -reset_timestamps 1 "p_%d.mp4"', shell=True)
        parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(x.split('_')[1].split('.')[0]))
        
        for i, p in enumerate(parts):
            is_last = (i == len(parts) - 1)
            # Label Logic
            if lang == 'my':
                label = f"အပိုင်း({i+1})" if not is_last else "ဇာတ်သိမ်းပိုင်း"
            else:
                label = f"Part-{i+1}" if not is_last else "End Part"
            
            vf = f"drawtext=text='{label}':fontcolor=white:fontsize=h/10:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
            if wm_text:
                vf += f",drawtext=text='{wm_text}':fontcolor=white@0.3:fontsize=h/22:x=w-text_w-20:y=h-text_h-20"
            
            subprocess.run(f'ffmpeg -y -i "{p}" -vf "{vf}" -c:v libx264 -crf 20 -c:a copy "out.mp4"', shell=True)
            
            caption = f"{movie_name} + {label} + {wm_text}" if wm_text else f"{movie_name} + {label}"
            with open("out.mp4", 'rb') as v:
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendVideo", data={'chat_id': user_id, 'caption': caption}, files={'video': v})
            os.remove(p); os.remove("out.mp4")

        os.remove("movie.mp4")
        task_doc.reference.update({'status': 'completed'})
    except: task_doc.reference.update({'status': 'error'})

if __name__ == "__main__": process()
