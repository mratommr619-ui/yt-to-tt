const admin = require('firebase-admin');
const youtubeDl = require('yt-dlp-exec');
const ffmpeg = require('fluent-ffmpeg');
const ffmpegPath = require('ffmpeg-static');
const fs = require('fs');
const path = require('path');

// FFmpeg လမ်းကြောင်းသတ်မှတ်ခြင်း
ffmpeg.setFfmpegPath(ffmpegPath);

// ၁။ Firebase Admin ကို ချိတ်ဆက်ခြင်း
// သင့် folder ထဲမှာ serviceAccountKey.json ရှိရပါမယ်
const serviceAccount = require('./serviceAccountKey.json');

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  storageBucket: "yttott-28862.appspot.com" // သင့် Firebase Bucket ID
});

const db = admin.firestore();

// ၂။ ဗီဒီယိုကို ၅ မိနစ်စီ ပိုင်းဖြတ်ပေးမယ့် Function
async function splitVideo(inputPath, outputFolder) {
    if (!fs.existsSync(outputFolder)) {
        fs.mkdirSync(outputFolder, { recursive: true });
    }
    
    return new Promise((resolve, reject) => {
        console.log("ဗီဒီယိုကို ၅ မိနစ်စီ စတင်ပိုင်းဖြတ်နေပါပြီ...");
        ffmpeg(inputPath)
            .outputOptions([
                '-f segment',
                '-segment_time 300', // ၃၀၀ စက္ကန့် = ၅ မိနစ်
                '-reset_timestamps 1',
                '-map 0',
                '-c copy' // အရည်အသွေးမကျအောင် copy သုံးခြင်း
            ])
            .output(path.join(outputFolder, 'part_%d.mp4'))
            .on('end', () => {
                console.log('✅ ဗီဒီယို ပိုင်းဖြတ်ခြင်း ပြီးဆုံးပါပြီ။');
                resolve();
            })
            .on('error', (err) => {
                console.error('❌ FFmpeg Error:', err);
                reject(err);
            })
            .run();
    });
}

// ၃။ အဓိက Run မယ့် Bot Function
async function startBot() {
    console.log("🚀 Bot စတင် အလုပ်လုပ်နေပါပြီ...");
    
    try {
        // Firestore ထဲက status: 'pending' ဖြစ်နေတဲ့ task တွေကို ဖတ်မယ်
        const tasksRef = db.collection('tasks');
        const snapshot = await tasksRef.where('status', '==', 'pending').get();

        if (snapshot.empty) {
            console.log('လုပ်ဆောင်စရာ Task အသစ် မရှိသေးပါ။');
            return;
        }

        for (const doc of snapshot.docs) {
            const data = doc.data();
            const videoUrl = data.videoUrl;
            const taskId = data.taskId || doc.id;
            
            const tempVideoPath = `./temp_${taskId}.mp4`;
            const outputFolder = `./parts_${taskId}`;

            console.log(`🎬 Processing Task: ${taskId}`);
            console.log(`🔗 YouTube URL: ${videoUrl}`);

            // အဆင့် (က) - YouTube မှ ဗီဒီယို ဒေါင်းလုဒ်ဆွဲခြင်း
            console.log("⏳ ဗီဒီယို ဒေါင်းလုဒ်ဆွဲနေသည်...");
            await youtubeDl(videoUrl, {
                output: tempVideoPath,
                format: 'mp4',
                noCheckCertificates: true,
            });

            // အဆင့် (ခ) - ဗီဒီယိုကို ၅ မိနစ်စီ ပိုင်းဖြတ်ခြင်း
            await splitVideo(tempVideoPath, outputFolder);

            // အဆင့် (ဂ) - ထွက်လာတဲ့ အပိုင်းတွေကို စာရင်းပြခြင်း
            const files = fs.readdirSync(outputFolder);
            console.log(`📦 အပိုင်းပေါင်း ${files.length} ပိုင်း ထွက်လာပါပြီ။ folder: ${outputFolder}`);

            // အဆင့် (ဃ) - Task ကို Completed လုပ်ခြင်း
            await tasksRef.doc(doc.id).update({ 
                status: 'completed',
                totalParts: files.length,
                processedAt: admin.firestore.FieldValue.serverTimestamp()
            });

            // ဒေါင်းထားတဲ့ မူရင်းဖိုင်ကြီးကို နေရာမရှုပ်အောင် ဖျက်ထုတ်ခြင်း
            if (fs.existsSync(tempVideoPath)) fs.unlinkSync(tempVideoPath);
            
            console.log(`✅ Task ${taskId} ပြီးမြောက်သွားပါပြီ။`);
        }

    } catch (error) {
        console.error("❌ Bot Error:", error);
    }
}

// Bot ကို စတင်မောင်းနှင်ခြင်း
startBot();
