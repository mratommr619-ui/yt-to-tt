import os
import json
import subprocess
import requests
import time
import firebase_admin
from firebase_admin import credentials, firestore
import yt_dlp

START_TIME = time.time()
TIMEOUT_SECONDS = 330 * 60 

# --- [၁] Firebase Setup ---
try:
    cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(cert_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except: exit(1)

# --- [၂] GitHub ကို ပြန်နှိုးမည့် Function ---
def restart_workflow():
    token = os.environ.get('GH_TOKEN')
    repo = "mratommr619-ui/yt-to-tt"
    url = f"https://api.github.com/repos/{repo}/actions/workflows/main.yml/dispatches"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    requests.post(url, headers=headers, json={"ref": "main"})
    print("🚀 Sent restart signal to GitHub Actions!")

# --- [၃] Fast Forward Telegram Sender ---
def send_to_telegram(video_path, caption):
    token = os.environ.get('TELEGRAM_TOKEN')
    raw_ids = os.environ.get('TELEGRAM_CHAT_ID', '')
    chat_ids = [cid.strip() for cid in raw_ids.split(',') if cid.strip()]
    
    if not chat_ids: return False

    # ၁။ ပထမဆုံး ID ဆီကို ဗီဒီယို အရင် Upload တင်မယ်
    first_id = chat_ids[0]
    upload_url = f"https://api.telegram.org/bot{token}/sendVideo"
    file_id = None
    
    try:
        print(f"📤 Uploading original video to: {first_id}...")
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {'chat_id': first_id, 'caption': caption}
            res = requests.post(upload_url, data=data, files=files).json()
            if res.get('ok'):
                # တင်ပြီးသွားရင် Telegram က ပေးတဲ့ file_id ကို မှတ်ထားမယ်
                file_id = res['result']['video']['file_id']
                print(f"✅ Uploaded! File ID: {file_id}")
            else:
                print(f"❌ Upload failed: {res}")
                return False
    except Exception as e:
        print(f"❌ Upload Error: {e}")
        return False

    # ၂။ ကျန်တဲ့ ID တွေဆီကို Forward (copyMessage) လုပ်မယ် (ဒါက အရမ်းမြန်တယ်)
    if file_id and len(chat_ids) > 1:
        forward_url = f"https://api.telegram.org/bot{token}/copyMessage"
        for cid in chat_ids[1:]:
            try:
                print(f"➡️ Fast Forwarding to: {cid}...")
                # copyMessage က Forward စာတန်း မပါဘဲ အသစ်တင်သလို ပို့ပေးတာပါ
                f_data = {
                    'chat_id': cid, 
                    'from_chat_id': first_id, 
                    'message_id': res['result']['message_id']
                }
                requests.post(forward_url, data=f_data)
            except Exception as e:
                print(f"⚠️ Forward error for {cid}: {e}")
                
    return True

# --- [၄] Universal Downloader ---
def download_universal_video(video_url):
    ydl_opts = {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 'outtmpl': 'movie.mp4', 'noplaylist': True, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([video_url])
        return True
    except: return False

# --- [၅] Main Process ---
def start_bot():
    tasks_ref = db.collection('tasks')
    while True:
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
                
                caption = f"{movie_name} - {label} {hashtags} @juneking619"
                if send_to_telegram("final.mp4", caption):
                    task_doc.reference.collection('parts').document(f'p{i}').update({'status': 'completed'})

                if os.path.exists(part_file): os.remove(part_file)
                if os.path.exists("final.mp4"): os.remove("final.mp4")

            if os.path.exists("movie.mp4"): os.remove("movie.mp4")
            task_doc.reference.update({'status': 'completed'})
        except:
            task_doc.reference.update({'status': 'error'})

if __name__ == "__main__":
    start_bot()
