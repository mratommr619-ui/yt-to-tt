import os
import json
import time
import subprocess
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from tiktok_uploader.upload import upload_video
import yt_dlp

# --- [၁] Firebase Setup ---
try:
    cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(cert_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"❌ Firebase Setup Error: {e}")
    exit(1)

# --- [၂] Telegram Sender ---
def send_to_telegram(video_path, caption):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    
    print(f"📤 Sending {video_path} to Telegram...")
    try:
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {'chat_id': chat_id, 'caption': caption}
            response = requests.post(url, data=data, files=files)
            
            if response.status_code == 200:
                return response.json()['result']['video']['file_id']
            else:
                raise Exception(response.text)
    except Exception as err:
        print(f"❌ Telegram API Error: {err}")
        return None

# --- [၃] TikTok Cloud Uploader ---
def upload_to_tiktok(video_path, caption):
    cookies_str = os.environ.get('TIKTOK_COOKIES')
    if not cookies_str:
        print("⚠️ No TikTok Cookies found. Skipping TikTok upload.")
        return False
        
    try:
        print(f"🚀 Cloud Uploading {video_path} to TikTok...")
        with open('auth.txt', 'w', encoding='utf-8') as f:
            f.write(cookies_str)
        
        # TikTok Library ကိုသုံးပြီး တင်ခြင်း
        upload_video(video_path, description=caption, cookies='auth.txt')
        print("✅ TikTok Upload Finished!")
        return True
    except Exception as e:
        print(f"❌ TikTok Upload Error: {e}")
        return False

# --- [၄] YouTube Downloader (Anti-Ban စနစ်ပါဝင်သည်) ---
def download_youtube_video(video_url):
    print("📥 Downloading YouTube video...")
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': 'movie.mp4',
        'noplaylist': True,
        # YouTube က Bot မှန်း မသိအောင် ကာကွယ်သည့်စနစ်များ
        'sleep_interval_requests': 1,
        'sleep_interval': 2,
        'max_sleep_interval': 5,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        'geo_bypass': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return True
    except Exception as e:
        print(f"❌ YouTube Download Error: {e}")
        return False

# --- [၅] Main Process ---
def start_bot():
    tasks_ref = db.collection('tasks')
    
    # Task အသစ် (Pending) ရှိမရှိ အရင်စစ်မယ်
    pending_query = list(tasks_ref.where('status', '==', 'pending').order_by('createdAt').limit(1).stream())
    
    task_doc = None
    if pending_query:
        task_doc = pending_query[0]
        video_url = task_doc.to_dict().get('videoUrl')
        try:
            # YouTube ကနေ Down မယ်
            if not download_youtube_video(video_url):
                task_doc.reference.update({'status': 'error'})
                return
            
            print("✂️ Splitting video into 5-minute parts...")
            subprocess.run('ffmpeg -i "movie.mp4" -c copy -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"', shell=True, check=True)
            
            # File တွေကို ရှာပြီး Database ထဲထည့်မယ်
            files = [f for f in os.listdir('.') if f.startswith('part_') and f.endswith('.mp4')]
            files.sort(key=lambda x: int(x.split('_')[1].split('.')[0])) # မှန်ကန်အောင် စီခြင်း
            
            for i, f in enumerate(files):
                label = "End Part" if i == len(files) - 1 else f"Part - {i+1}"
                task_doc.reference.collection('parts').document(f'p{i}').set({
                    'fileIndex': i, 'label': label, 'status': 'pending'
                })
            
            task_doc.reference.update({'status': 'processing'})
            if os.path.exists("movie.mp4"): os.remove("movie.mp4")
            
        except Exception as e:
            print(f"❌ Split Error: {e}")
            task_doc.reference.update({'status': 'error'})
            return
    else:
        # Processing ဖြစ်နေတဲ့ Task ထဲက အပိုင်းတွေကို ဆက်လုပ်မယ်
        proc_query = list(tasks_ref.where('status', '==', 'processing').order_by('createdAt').limit(1).stream())
        if not proc_query:
            print("💤 No tasks to do.")
            return
        task_doc = proc_query[0]

    data = task_doc.to_dict()
    movie_name = data.get('movieName', '')
    hashtags = data.get('hashtags', '#fyp #movie')
    
    parts_ref = task_doc.reference.collection('parts')
    pending_parts = list(parts_ref.where('status', '==', 'pending').order_by('fileIndex').limit(1).stream())

    if pending_parts:
        part_doc = pending_parts[0]
        p_data = part_doc.to_dict()
        file_index = p_data.get('fileIndex')
        label = p_data.get('label')
        part_file = f"part_{file_index}.mp4"

        if os.path.exists(part_file):
            try:
                print(f"🎬 Processing {label}...")
                movie_label = f"drawtext=text='{movie_name}':fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=h-80"
                part_label = f"drawtext=text='{label}':fontcolor=white:fontsize=80:borderw=4:bordercolor=red:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
                
                # စာသားထည့်ခြင်း
                subprocess.run(f'ffmpeg -y -i "{part_file}" -vf "{part_label},{movie_label}" "final.mp4"', shell=True, check=True)

                caption = f"{movie_name} - {label} {hashtags} @juneking619"
                
                # ၁။ Telegram ပို့ခြင်း (Backup ရယူရန်)
                file_id = send_to_telegram("final.mp4", caption)
                
                # ၂။ TikTok သို့ တိုက်ရိုက်တင်ခြင်း
                upload_to_tiktok("final.mp4", caption)
                
                # Firestore Update
                part_doc.reference.update({ 
                    'status': 'completed', # ဖုန်းနဲ့ မလိုတော့လို့ completed လို့ တန်းပြောင်းလိုက်ပါတယ်
                    'tg_file_id': file_id,
                    'caption': caption,
                    'readyAt': firestore.SERVER_TIMESTAMP
                })
                print(f"✅ {label} successfully processed!")
                
            except Exception as err:
                print(f"❌ Processing failed: {err}")
            
            # ဖိုင်ဟောင်းများကို ရှင်းလင်းခြင်း
            if os.path.exists(part_file): os.remove(part_file)
            if os.path.exists("final.mp4"): os.remove("final.mp4")
            if os.path.exists("auth.txt"): os.remove("auth.txt")

        # အပိုင်းအားလုံးပြီးသွားရင် Task ကို Completed ပြောင်းမယ်
        remain = list(parts_ref.where('status', '==', 'pending').stream())
        if len(remain) == 0:
            task_doc.reference.update({'status': 'completed'})
            print("🏁 All parts sent to Telegram & TikTok.")

if __name__ == "__main__":
    start_bot()
