import os
import json
import subprocess
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

# --- [၂] TikTok Cloud Uploader ---
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

# --- [၃] Universal Video Downloader ---
def download_universal_video(video_url):
    print(f"📥 Downloading video from: {video_url}")
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': 'movie.mp4',
        'noplaylist': True,
        'geo_bypass': True,
        'quiet': False
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        print("✅ Video Downloaded Successfully!")
        return True
    except Exception as e:
        print(f"❌ Universal Download Error: {e}")
        return False

# --- [၄] Main Process ---
def start_bot():
    tasks_ref = db.collection('tasks')
    pending_query = list(tasks_ref.where('status', '==', 'pending').order_by('createdAt').limit(1).stream())
    
    task_doc = None
    if pending_query:
        task_doc = pending_query[0]
        video_url = task_doc.to_dict().get('videoUrl')
        try:
            if not download_universal_video(video_url):
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
    
    safe_movie_name = movie_name.replace("'", "’").replace('"', '”')
    
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

                movie_label = f"drawtext=text='{safe_movie_name}':fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=h-80"
                part_label = f"drawtext=text='{label}':fontcolor=white:fontsize=80:borderw=4:bordercolor=red:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
                
                subprocess.run(f'ffmpeg -y -i "{part_file}" -vf "{moving_watermark},{movie_label},{part_label}" "final.mp4"', shell=True, check=True)

                caption = f"{movie_name} - {label} {hashtags} @juneking619"
                
                # TikTok သို့ တိုက်ရိုက်တင်ခြင်း (Telegram မပါတော့ပါ)
                upload_to_tiktok("final.mp4", caption)
                
                part_doc.reference.update({ 
                    'status': 'completed',
                    'caption': caption,
                    'readyAt': firestore.SERVER_TIMESTAMP
                })
                print(f"✅ {label} finished and uploaded!")
                
            except Exception as err:
                print(f"❌ Processing failed: {err}")
            
            # Temporary files များကို ပြန်ဖျက်ခြင်း
            if os.path.exists(part_file): os.remove(part_file)
            if os.path.exists("final.mp4"): os.remove("final.mp4")
            if os.path.exists("auth.txt"): os.remove("auth.txt")

        # အပိုင်းများအားလုံး ပြီးဆုံးပါက Task ကို Completed ပြောင်းခြင်း
        remain = list(parts_ref.where('status', '==', 'pending').stream())
        if len(remain) == 0:
            task_doc.reference.update({'status': 'completed'})
            print("🏁 Task Completed: All parts cleaned and uploaded.")

if __name__ == "__main__":
    start_bot()
