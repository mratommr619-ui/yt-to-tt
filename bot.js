const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const axios = require('axios');

// --- [၁] Firebase Setup ---
try {
    const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
    admin.initializeApp({ credential: admin.credential.cert(serviceAccount) });
} catch (e) { process.exit(1); }
const db = admin.firestore();

// --- [၂] Telegram Sender ---
async function sendToTelegram(videoPath, caption) {
    const FormData = require('form-data');
    const formData = new FormData();
    formData.append('chat_id', process.env.TELEGRAM_CHAT_ID);
    formData.append('video', fs.createReadStream(videoPath));
    formData.append('caption', caption);

    try {
        console.log(`📤 Sending ${videoPath} to Telegram...`);
        const res = await axios.post(`https://api.telegram.org/bot${process.env.TELEGRAM_TOKEN}/sendVideo`, formData, {
            headers: formData.getHeaders(),
            maxContentLength: Infinity,
            maxBodyLength: Infinity
        });
        return res.data.result.video.file_id;
    } catch (err) {
        console.error("❌ Telegram Error:", err.response?.data || err.message);
        throw err;
    }
}

// --- [၃] Downloader ---
function downloadVideo(url, output) {
    console.log("🔄 Updating yt-dlp & Downloading...");
    try { execSync(`pip install -U yt-dlp`, { stdio: 'inherit' }); } catch (e) {}
    execSync(`yt-dlp --no-check-certificate "${url}" -o "temp_raw.mp4"`, { stdio: 'inherit' });
    if (fs.existsSync('temp_raw.mp4')) fs.renameSync('temp_raw.mp4', output);
}

// --- [၄] Main Logic ---
async function startBot() {
    let taskSnap = await db.collection('tasks').where('status', '==', 'pending').orderBy('createdAt', 'asc').limit(1).get();
    let taskDoc;

    if (!taskSnap.empty) {
        taskDoc = taskSnap.docs[0];
        try {
            downloadVideo(taskDoc.data().videoUrl, "movie.mp4");
            // ဗီဒီယိုဖြတ်မယ် (၅ မိနစ်စာစီ)
            execSync(`ffmpeg -i "movie.mp4" -c copy -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
            const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
            for (let i = 0; i < files.length; i++) {
                const label = (i === files.length - 1) ? "End Part" : `Part - ${i+1}`;
                await taskDoc.ref.collection('parts').doc(`p${i}`).set({ 
                    fileIndex: i, label: label, status: 'pending' 
                });
            }
            await taskDoc.ref.update({ status: 'processing' });
            if (fs.existsSync("movie.mp4")) fs.unlinkSync("movie.mp4");
        } catch (e) { await taskDoc.ref.update({ status: 'error' }); return; }
    } else {
        const procSnap = await db.collection('tasks').where('status', '==', 'processing').orderBy('createdAt', 'asc').limit(1).get();
        if (procSnap.empty) return;
        taskDoc = procSnap.docs[0];
    }

    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex', 'asc').limit(1).get();
    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        const partFile = `part_${fileIndex}.mp4`;
        
        if (fs.existsSync(partFile)) {
            try {
                const movieName = taskDoc.data().movieName;
                const watermark = "@juneking619";
                const movieLabel = `drawtext=text='${movieName}':fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=h-80`;
                const partLabel = `drawtext=text='${label}':fontcolor=white:fontsize=80:borderw=4:bordercolor=red:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'`;
                
                console.log(`🎬 Adding Watermark to ${label}...`);
                execSync(`ffmpeg -y -i "${partFile}" -vf "${partLabel},${movieLabel}" "final.mp4"`);

                const caption = `${movieName} - ${label} ${taskDoc.data().hashtags || "#fyp #movie"} @juneking619`;
                
                // Telegram ကို ပို့မယ်
                const fileId = await sendToTelegram("final.mp4", caption);
                
                // Firebase မှာ ဖုန်းကယူတင်ဖို့ Status ပြောင်းမယ်
                await partDoc.ref.update({ 
                    status: 'ready_for_phone',
                    tg_file_id: fileId,
                    caption: caption
                });

                console.log(`✅ ${label} sent to Telegram & Task updated.`);
            } catch (err) { console.log("❌ Failed to process part."); }
            
            if (fs.existsSync(partFile)) fs.unlinkSync(partFile);
            if (fs.existsSync("final.mp4")) fs.unlinkSync("final.mp4");
        }
    }
}
startBot();
