import os
import json
import subprocess
import requests
import time
import firebase_admin
from firebase_admin import credentials, firestore
import yt_dlp

START_TIME = time.time()
TIMEOUT_SECONDS = 330 * 60 # ၅ နာရီခွဲ (၁၉၈၀၀ စက္ကန့်)

# --- [၁] Firebase Setup ---
try:
    cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(cert_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except:
    exit(1)

# --- [၂] GitHub ကို ပြန်နှိုးမည့် Function ---
def restart_workflow():
    token = os.environ.get('GH_TOKEN')
    repo = "mratommr619-ui/yt-to-tt" # မိတ်ဆွေရဲ့ Repo လိပ်စာ
    url = f"https://api.github.com/repos/{repo}/actions/workflows/main.yml/dispatches"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"ref": "main"}
    requests.post(url, headers=headers, json=data)
    print("🚀 Sent restart signal to GitHub Actions!")

def send_to_telegram(video_path, caption):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    try:
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {'chat_id': chat_id, 'caption': caption}
            requests.post(url, data=data, files=files)
            return True
    except: return False

def download_universal_video(video_url):
    ydl_opts = {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 'outtmpl': 'movie.mp4', 'noplaylist': True, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([video_url])
        return True
    except: return False

def start_bot():
    tasks_ref = db.collection('tasks')
    while True:
        # အချိန်စစ်မယ် - ၅ နာရီခွဲပြည့်ရင် GitHub ကို နှိုးပြီး ပိတ်မယ်
        if (time.time() - START_TIME) > TIMEOUT_SECONDS:
            restart_workflow()
            break 

        pending_query = list(tasks_ref.where('status', '==', 'pending').order_by('createdAt').limit(1).stream())
        if not pending_query:
            time.sleep(15)
            continue

        task_doc = pending_query[0]
        data = task_doc.to_dict()
        video_url = data.get('videoUrl')
        movie_name = data.get('movieName', '')
        hashtags = data.get('hashtags', '#fyp #movie')
        safe_movie_name = movie_name.replace("'", "’").replace('"', '”')
        task_doc.reference.update({'status': 'processing'})

        if not download_universal_video(video_url):
            task_doc.reference.update({'status': 'error'})
            continue
        
        try:
            subprocess.run('ffmpeg -i "movie.mp4" -c copy -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"', shell=True, check=True)
            files = [f for f in os.listdir('.') if f.startswith('part_') and f.endswith('.mp4')]
            files.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))
            
            for i, _ in enumerate(files):
                task_doc.reference.collection('parts').document(f'p{i}').set({'fileIndex': i, 'label': f"Part - {i+1}", 'status': 'pending'})

            for i, part_file in enumerate(files):
                label = f"Part - {i+1}"
                task_doc.reference.collection('parts').document(f'p{i}').update({'status': 'processing'})
                
                moving_wm = "drawtext=text='@juneking619':fontcolor=white@0.4:fontsize=35:x='if(lt(mod(t,20),10),10+(w-text_w-20)*(mod(t,10)/10),w-text_w-10-(w-text_w-20)*(mod(t,10)/10))':y='if(lt(mod(t,14),7),10+(h-text_h-20)*(mod(t,7)/7),h-text_h-10-(h-text_h-20)*(mod(t,7)/7))'"
                movie_lb = f"drawtext=text='{safe_movie_name}':fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=h-80"
                part_lb = f"drawtext=text='{label}':fontcolor=white:fontsize=80:borderw=4:bordercolor=red:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
                
                subprocess.run(f'ffmpeg -y -i "{part_file}" -vf "{moving_wm},{movie_lb},{part_lb}" "final.mp4"', shell=True, check=True)
                if send_to_telegram("final.mp4", f"{movie_name} - {label} {hashtags} @juneking619"):
                    task_doc.reference.collection('parts').document(f'p{i}').update({'status': 'completed'})

                if os.path.exists(part_file): os.remove(part_file)
                if os.path.exists("final.mp4"): os.remove("final.mp4")

            if os.path.exists("movie.mp4"): os.remove("movie.mp4")
            task_doc.reference.update({'status': 'completed'})
        except:
            task_doc.reference.update({'status': 'error'})

if __name__ == "__main__":
    start_bot()
