import os
import json
import subprocess
import requests
import firebase_admin
from firebase_admin import credentials, firestore

# Setup
cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
cred = credentials.Certificate(cert_dict)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()
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
    
    # Download
    res = requests.get(f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={data['file_id']}").json()
    video_url = f"https://api.telegram.org/file/bot{TOKEN}/{res['result']['file_path']}"
    with requests.get(video_url, stream=True) as r:
        with open("movie.mp4", 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)

    try:
        # Split
        subprocess.run(f'ffmpeg -i "movie.mp4" -c copy -f segment -segment_time {split_time} -reset_timestamps 1 "p_%d.mp4"', shell=True)
        parts = sorted([f for f in os.listdir('.') if f.startswith('p_')], key=lambda x: int(x.split('_')[1].split('.')[0]))
        num_parts = len(parts)

        # Status Message
        status_txt = f"✅ ဗီဒီယိုကို အပိုင်း ({num_parts}) ပိုင်း ရရှိပါသည်။ အစဉ်အတိုင်း ပို့ဆောင်ပေးသွားပါမည်။" if lang == 'my' else f"✅ Video split into ({num_parts}) parts. Sending in order..."
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={'chat_id': user_id, 'text': status_txt})

        for i, p in enumerate(parts):
            is_last = (i == num_parts - 1)
            # Caption & Label Logic
            if lang == 'my':
                label = f"အပိုင်း({i+1})" if not is_last else "ဇာတ်သိမ်းပိုင်း"
            else:
                label = f"Part-{i+1}" if not is_last else "End Part"
            
            caption = f"{movie_name} + {label}"
            if wm_text: caption += f" + {wm_text}"

            vf = f"drawtext=text='{label}':fontcolor=white:fontsize=h/10:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
            if wm_text: vf += f",drawtext=text='{wm_text}':fontcolor=white@0.3:fontsize=h/22:x=w-text_w-20:y=h-text_h-20"
            
            subprocess.run(f'ffmpeg -y -i "{p}" -vf "{vf}" -c:v libx264 -crf 20 -c:a copy "out.mp4"', shell=True)
            with open("out.mp4", 'rb') as v:
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendVideo", data={'chat_id': user_id, 'caption': caption}, files={'video': v})
            os.remove(p); os.remove("out.mp4")

        os.remove("movie.mp4")
        task_doc.reference.update({'status': 'completed'})
    except: task_doc.reference.update({'status': 'error'})

if __name__ == "__main__": process()
