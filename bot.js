const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const axios = require('axios');
const FormData = require('form-data');

// --- [၁] Firebase Setup ---
try {
    const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
    admin.initializeApp({ credential: admin.credential.cert(serviceAccount) });
} catch (e) {
    console.error("❌ Firebase Setup Error:", e.message);
    process.exit(1);
}
const db = admin.firestore();

// --- [၂] Telegram Sender ---
async function sendToTelegram(videoPath, caption) {
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
        console.error("❌ Telegram API Error:", err.response?.data || err.message);
        throw err;
    }
}

// --- [၃] Main Process ---
async function startBot() {
    // Task အသစ် (Pending) ရှိမရှိ အရင်စစ်မယ်
    let taskSnap = await db.collection('tasks').where('status', '==', 'pending').orderBy('createdAt', 'asc').limit(1).get();
    let taskDoc;

    if (!taskSnap.empty) {
        taskDoc = taskSnap.docs[0];
        const { videoUrl } = taskDoc.data();
        try {
            console.log("📥 Downloading video...");
            execSync(`yt-dlp --no-check-certificate "${videoUrl}" -o "movie.mp4"`, { stdio: 'inherit' });
            
            console.log("✂️ Splitting video into 5-minute parts...");
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
        } catch (e) {
            console.error("❌ Split Error:", e.message);
            await taskDoc.ref.update({ status: 'error' });
            return;
        }
    } else {
        // Processing ဖြစ်နေတဲ့ Task ထဲက အပိုင်းတွေကို ဆက်ပို့မယ်
        const procSnap = await db.collection('tasks').where('status', '==', 'processing').orderBy('createdAt', 'asc').limit(1).get();
        if (procSnap.empty) return console.log("💤 No tasks to do.");
        taskDoc = procSnap.docs[0];
    }

    const { movieName, hashtags } = taskDoc.data();
    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex', 'asc').limit(1).get();

    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        const partFile = `part_${fileIndex}.mp4`;

        if (fs.existsSync(partFile)) {
            try {
                console.log(`🎬 Processing ${label}...`);
                const movieLabel = `drawtext=text='${movieName}':fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=h-80`;
                const partLabel = `drawtext=text='${label}':fontcolor=white:fontsize=80:borderw=4:bordercolor=red:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)'`;
                
                // စာသားထည့်ခြင်း
                execSync(`ffmpeg -y -i "${partFile}" -vf "${partLabel},${movieLabel}" "final.mp4"`);

                const caption = `${movieName} - ${label} ${hashtags || "#fyp #movie"} @juneking619`;
                
                // Telegram ပို့ခြင်း
                const fileId = await sendToTelegram("final.mp4", caption);
                
                // Firestore Update (MacroDroid အတွက် Status အသစ်)
                await partDoc.ref.update({ 
                    status: 'ready_for_phone',
                    tg_file_id: fileId,
                    caption: caption,
                    readyAt: admin.firestore.FieldValue.serverTimestamp()
                });

                console.log(`✅ ${label} sent to Telegram!`);
            } catch (err) {
                console.error("❌ Processing failed:", err.message);
            }
            
            // Clean up files
            if (fs.existsSync(partFile)) fs.unlinkSync(partFile);
            if (fs.existsSync("final.mp4")) fs.unlinkSync("final.mp4");
        }

        // အပိုင်းအားလုံးပြီးသွားရင် Task ကို Completed ပြောင်းမယ်
        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').get();
        if (remain.size === 0) {
            await taskDoc.ref.update({ status: 'completed' });
            console.log("🏁 All parts sent to Telegram.");
        }
    }
}

startBot();
