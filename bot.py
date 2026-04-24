import os
import json
import subprocess
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import yt_dlp

# --- [၁] Firebase Setup ---
try:
    cert_dict = json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(cert_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"❌ Firebase Error: {e}")
    exit(1)

# --- [၂] Fast Forward Telegram Sender ---
def send_to_telegram(video_path, caption):
    token = os.environ.get('TELEGRAM_TOKEN')
    raw_ids = os.environ.get('TELEGRAM_CHAT_ID', '')
    chat_ids = [cid.strip() for cid in raw_ids.split(',') if cid.strip()]
    
    if not chat_ids:
        print("❌ No Target IDs found!")
        return False

    first_id = chat_ids[0]
    upload_url = f"https://api.telegram.org/bot{token}/sendVideo"
    
    try:
        print(f"📤 Uploading to primary: {first_id}...")
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {'chat_id': first_id, 'caption': caption}
            res = requests.post(upload_url, data=data, files=files).json()
            
            if res.get('ok'):
                msg_id = res['result']['message_id']
                # ကျန်တဲ့ ID တွေဆီကို Fast Forward (copyMessage) လုပ်ခြင်း
                if len(chat_ids) > 1:
                    copy_url = f"https://api.telegram.org/bot{token}/copyMessage"
                    for cid in chat_ids[1:]:
                        try:
                            print(f"➡️ Copying to: {cid}...")
                            requests.post(copy_url, data={
                                'chat_id': cid, 
                                'from_chat_id': first_id, 
                                'message_id': msg_id
                            })
                        except: pass
                return True
            else:
                print(f"❌ Upload failed: {res.get('description')}")
                return False
    except Exception as e:
        print(f"❌ Sender Error: {e}")
        return False

# --- [၃] Video Downloader ---
def download_video(video_url):
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': 'movie.mp4',
        'quiet': True,
        'noplaylist': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return True
    except:
        return False

# --- [၄] Main Process (Task Manager) ---
def start_bot():
    tasks_ref = db.collection('tasks')
    print("🔎 Checking Firestore for pending tasks...")
    
    # Pending ဖြစ်နေတဲ့ Task အားလုံးကို အစဉ်လိုက်ယူမယ်
    query = tasks_ref.where('status', '==', 'pending').order_by('createdAt').get()
    
    if not query:
        print("✅ No pending tasks. System shutting down to save resources.")
        return # အလုပ်မရှိရင် ဒီမှာတင် ရပ်မယ် (GitHub အစိမ်းရောင်ပြမယ်)

    for task_doc in query:
        data = task_doc.to_dict()
        movie_name = data.get('movieName', 'Movie')
        hashtags = data.get('hashtags', '#fyp #movie')
        safe_name = movie_name.replace("'", "’")
        
        print(f"🎬 Processing Movie: {movie_name}")
        task_doc.reference.update({'status': 'processing'})

        if not download_video(data.get('videoUrl')):
            task_doc.reference.update({'status': 'error'})
            continue
        
        try:
            # ဗီဒီယို ဖြတ်တောက်ခြင်း
            subprocess.run('ffmpeg -i "movie.mp4" -c copy -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"', shell=True, check=True)
            files = sorted([f for f in os.listdir('.') if f.startswith('part_') and f.endswith('.mp4')], key=lambda x: int(x.split('_')[1].split('.')[0]))
            
            # Dashboard မှာ အပိုင်းများ ကြိုတင်သတ်မှတ်ခြင်း
            for i, _ in enumerate(files):
                task_doc.reference.collection('parts').document(f'p{i}').set({
                    'fileIndex': i, 'label': f"Part - {i+1}", 'status': 'pending'
                })

            # တစ်ပိုင်းချင်းစီ Watermark ထည့်ပြီး ပို့ခြင်း
            for i, part_file in enumerate(files):
                label = f"Part - {i+1}"
                task_doc.reference.collection('parts').document(f'p{i}').update({'status': 'processing'})
                
                moving_wm = "drawtext=text='@juneking619':fontcolor=white@0.4:fontsize=35:x='if(lt(mod(t,20),10),10+(w-text_w-20)*(mod(t,10)/10),w-text_w-10-(w-text_w-20)*(mod(t,10)/10))':y='if(lt(mod(t,14),7),10+(h-text_h-20)*(mod(t,7)/7),h-text_h-10-(h-text_h-20)*(mod(t,7)/7))'"
                movie_lb = f"drawtext=text='{safe_name}':fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=h-80"
                part_lb = f"drawtext=text='{label}':fontcolor=white:fontsize=80:borderw=4:bordercolor=red:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
                
                subprocess.run(f'ffmpeg -y -i "{part_file}" -vf "{moving_wm},{movie_lb},{part_lb}" "final.mp4"', shell=True, check=True)
                
                caption = f"{movie_name} - {label} {hashtags} @juneking619"
                if send_to_telegram("final.mp4", caption):
                    task_doc.reference.collection('parts').document(f'p{i}').update({'status': 'completed'})
                
                if os.path.exists(part_file): os.remove(part_file)
                if os.path.exists("final.mp4"): os.remove("final.mp4")

            if os.path.exists("movie.mp4"): os.remove("movie.mp4")
            task_doc.reference.update({'status': 'completed'})
            print(f"✅ Successfully finished: {movie_name}")

        except Exception as e:
            print(f"❌ Error processing {movie_name}: {e}")
            task_doc.reference.update({'status': 'error'})

if __name__ == "__main__":
    start_bot()
