import os
import json
import subprocess
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from tiktok_uploader.upload import upload_video

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
        
        upload_video(video_path, description=caption, cookies='auth.txt')
        print("✅ TikTok Upload Finished!")
        return True
    except Exception as e:
        print(f"❌ TikTok Upload Error: {e}")
        return False

# --- [၄] API Downloader (No yt-dlp, No Cookies needed) ---
def download_youtube_video(video_url):
    print("📥 Bypassing yt-dlp using Cobalt API...")
    api_url = "https://api.cobalt.tools/api/json"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://cobalt.tools",
        "Referer": "https://cobalt.tools/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    data = {
        "url": video_url,
        "vQuality": "720", 
        "isAudioOnly": False
    }
    
    try:
        res = requests.post(api_url, json=data, headers=headers)
        result = res.json()
        
        if "url" not in result:
            print(f"❌ API Error: {result}")
            return False
            
        download_url = result["url"]
        print("📥 Direct Link Found! Downloading MP4...")
        
        video_data = requests.get(download_url, stream=True)
        with open("movie.mp4", 'wb') as f:
            for chunk in video_data.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
                    
        print("✅ Video Downloaded Successfully!")
        return True
    except Exception as e:
        print(f"❌ Download Error: {e}")
        return False

# --- [၅] Main Process ---
def start_bot():
    tasks_ref = db.collection('tasks')
    pending_query = list(tasks_ref.where('status', '==', 'pending').order_by('createdAt').limit(1).stream())
    
    task_doc = None
    if pending_query:
        task_doc = pending_query[0]
        video_url = task_doc.to_dict().get('videoUrl')
        try:
            if not download_youtube_video(video_url):
                task_doc.reference.update({'status': 'error'})
                return
            
            print("✂️ Splitting video into 5-minute parts...")
            subprocess.run('ffmpeg -i "movie.mp4" -c copy -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"', shell=True, check=True)
            
            files = [f for f in os.listdir('.') if f.startswith('part_') and f.endswith('.mp4')]
            files.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))
            
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
                print(f"🎬 Processing {label} with Moving Watermark...")
                
                moving_watermark = (
                    "drawtext=text='@juneking619':fontcolor=white@0.4:fontsize=35:"
                    "x='if(lt(mod(t,20),10),10+(w-text_w-20)*(mod(t,10)/10),w-text_w-10-(w-text_w-20)*(mod(t,10)/10))':"
                    "y='if(lt(mod(t,14),7),10+(h-text_h-20)*(mod(t,7)/7),h-text_h-10-(h-text_h-20)*(mod(t,7)/7))'"
                )

                movie_label = f"drawtext=text='{movie_name}':fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=h-80"
                part_label = f"drawtext=text='{label}':fontcolor=white:fontsize=80:borderw=4:bordercolor=red:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
                
                subprocess.run(f'ffmpeg -y -i "{part_file}" -vf "{moving_watermark},{movie_label},{part_label}" "final.mp4"', shell=True, check=True)

                caption = f"{movie_name} - {label} {hashtags} @juneking619"
                
                file_id = send_to_telegram("final.mp4", caption)
                upload_to_tiktok("final.mp4", caption)
                
                part_doc.reference.update({ 
                    'status': 'completed',
                    'tg_file_id': file_id,
                    'caption': caption,
                    'readyAt': firestore.SERVER_TIMESTAMP
                })
                print(f"✅ {label} finished and uploaded!")
                
            except Exception as err:
                print(f"❌ Processing failed: {err}")
            
            if os.path.exists(part_file): os.remove(part_file)
            if os.path.exists("final.mp4"): os.remove("final.mp4")
            if os.path.exists("auth.txt"): os.remove("auth.txt")

        remain = list(parts_ref.where('status', '==', 'pending').stream())
        if len(remain) == 0:
            task_doc.reference.update({'status': 'completed'})
            print("🏁 Task Completed: All parts cleaned and uploaded.")

if __name__ == "__main__":
    start_bot()
