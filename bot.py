import os
import json
import subprocess
import requests
import time
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
    print(f"❌ Firebase Setup Error: {e}")
    exit(1)

# --- [၂] Telegram Sender ---
def send_to_telegram(video_path, caption):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    
    print(f"📤 Sending to Telegram...")
    try:
        with open(video_path, 'rb') as video_file:
            files = {'video': video_file}
            data = {'chat_id': chat_id, 'caption': caption}
            response = requests.post(url, data=data, files=files)
            if response.status_code == 200:
                return True
            else:
                raise Exception(response.text)
    except Exception as err:
        print(f"❌ Telegram API Error: {err}")
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

# --- [၄] Main Auto-Queue Process ---
def start_bot():
    tasks_ref = db.collection('tasks')
    
    print("🚀 Bot Started! Waiting for tasks...")
    
    # ထာဝရ အလုပ်လုပ်မည့် (Infinite Loop) စနစ်
    while True:
        # ၁။ Pending ဖြစ်နေတဲ့ ဇာတ်ကား "တစ်ကား" ကို ဆွဲထုတ်မယ် (အဟောင်းဆုံးကနေ စလုပ်ပါမည်)
        pending_query = list(tasks_ref.where('status', '==', 'pending').order_by('createdAt').limit(1).stream())
        
        # Database ထဲမှာ Pending မရှိတော့ရင် ၁၀ စက္ကန့်နားပြီး Link အသစ် ဝင်လာမလား ထပ်စစ်မယ်
        if not pending_query:
            print("💤 No pending tasks. Waiting 10 seconds for new links...")
            time.sleep(10)
            continue # အောက်က Code တွေကို မလုပ်ဘဲ အပေါ်ကနေ ပြန်စစ်မည်

        # Task ရှိခဲ့ရင် စတင် အလုပ်လုပ်မည်
        task_doc = pending_query[0]
        data = task_doc.to_dict()
        video_url = data.get('videoUrl')
        movie_name = data.get('movieName', '')
        hashtags = data.get('hashtags', '#fyp #movie')
        
        # ဇာတ်လမ်းနာမည်ထဲက Quote (') တွေကြောင့် FFmpeg error မတက်အောင် ပြင်ခြင်း
        safe_movie_name = movie_name.replace("'", "’").replace('"', '”')

        print(f"\n==========================================")
        print(f"🎬 New Task Started: {movie_name}")
        print(f"==========================================")
        
        # Status ကို processing လို့ ပြောင်းမယ် (နောက်တစ်ခေါက် Loop ပတ်ရင် ဒါကို ထပ်မယူတော့အောင်)
        task_doc.reference.update({'status': 'processing'})

        # ၂။ Video ကို ဒေါင်းမယ်
        if not download_universal_video(video_url):
            print(f"❌ Skipping {movie_name} due to download error.")
            task_doc.reference.update({'status': 'error'})
            time.sleep(5)
            continue # Error တက်သွားရင် ဒီကားကို ကျော်ပြီး နောက်တစ်ကားကို ဆက်လုပ်မယ်
        
        try:
            # ၃။ ၅ မိနစ်စာ အပိုင်းလေးတွေ ဖြတ်မယ်
            print("✂️ Splitting video into 5-minute parts...")
            subprocess.run('ffmpeg -i "movie.mp4" -c copy -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"', shell=True, check=True)
            
            files = [f for f in os.listdir('.') if f.startswith('part_') and f.endswith('.mp4')]
            files.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))
            
            # ၄။ အပိုင်း တစ်ခုချင်းစီကို တောက်လျှောက် ပို့မယ်
            for i, part_file in enumerate(files):
                label = "End Part" if i == len(files) - 1 else f"Part - {i+1}"
                print(f"\n⚡ Processing {label}...")
                
                # --- Moving Watermark Logic (@juneking619 သည် ဗီဒီယိုအနှံ့ ပတ်ပြေးနေမည်) ---
                moving_watermark = (
                    "drawtext=text='@juneking619':fontcolor=white@0.4:fontsize=35:"
                    "x='if(lt(mod(t,20),10),10+(w-text_w-20)*(mod(t,10)/10),w-text_w-10-(w-text_w-20)*(mod(t,10)/10))':"
                    "y='if(lt(mod(t,14),7),10+(h-text_h-20)*(mod(t,7)/7),h-text_h-10-(h-text_h-20)*(mod(t,7)/7))'"
                )
                
                # Movie Name Label (အောက်ခြေ)
                movie_label = f"drawtext=text='{safe_movie_name}':fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=h-80"
                
                # Part Label (အလယ်တွင် ၃ စက္ကန့်)
                part_label = f"drawtext=text='{label}':fontcolor=white:fontsize=80:borderw=4:bordercolor=red:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'"
                
                # FFmpeg ဖြင့် ဗီဒီယိုထဲသို့ Watermark များ ထည့်ပေါင်းခြင်း
                subprocess.run(f'ffmpeg -y -i "{part_file}" -vf "{moving_watermark},{movie_label},{part_label}" "final.mp4"', shell=True, check=True)

                caption = f"{movie_name} - {label} {hashtags} @juneking619"
                
                # Telegram ကို ချက်ချင်းပို့ခြင်း
                if send_to_telegram("final.mp4", caption):
                    print(f"✅ {label} sent successfully!")
                else:
                    print(f"❌ {label} send failed.")

                # ပို့ပြီးသားဖိုင်များကို ချက်ချင်းပြန်ဖျက်ခြင်း
                if os.path.exists(part_file): os.remove(part_file)
                if os.path.exists("final.mp4"): os.remove("final.mp4")

            # ဇာတ်ကားတစ်ကားလုံး ပြီးသွားလျှင် Cleanup လုပ်ခြင်း
            if os.path.exists("movie.mp4"): os.remove("movie.mp4")
            task_doc.reference.update({'status': 'completed'})
            print(f"🏁 Completely Finished: {movie_name}")
            print(f"➡️ Looking for the next movie in queue...\n")
            
            time.sleep(3) # နောက်တစ်ကား မစခင် ၃ စက္ကန့်လောက် နားပေးမည်

        except Exception as e:
            print(f"❌ Split/Process Error: {e}")
            task_doc.reference.update({'status': 'error'})
            if os.path.exists("movie.mp4"): os.remove("movie.mp4")
            time.sleep(5)
            continue # Error တက်ရင်လည်း ရပ်မသွားဘဲ နောက်တစ်ကားကို ဆက်လုပ်မည်

if __name__ == "__main__":
    start_bot()
