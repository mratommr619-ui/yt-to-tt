const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// ၁။ Firebase Admin ကို ချိတ်ဆက်ခြင်း
// GitHub workflow ကနေ serviceAccountKey.json ကို အလိုအလျောက် ဆောက်ပေးပါလိမ့်မယ်
const serviceAccount = require('./serviceAccountKey.json');

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  storageBucket: "yttott-28862.appspot.com"
});

const db = admin.firestore();

// ၂။ ဗီဒီယိုကို ၅ မိနစ်စီ ပိုင်းဖြတ်ပေးမယ့် Function (Linux Command သုံးထားသည်)
async function splitVideo(inputPath, outputFolder) {
    if (!fs.existsSync(outputFolder)) {
        fs.mkdirSync(outputFolder, { recursive: true });
    }
    
    console.log("🎬 ဗီဒီယိုကို ၅ မိနစ်စီ စတင်ပိုင်းဖြတ်နေပါပြီ...");
    try {
        // GitHub Linux မှာ ffmpeg က အဆင်သင့်ရှိလို့ တိုက်ရိုက် command နဲ့ ဖြတ်တာ ပိုမြန်တယ်
        const command = `ffmpeg -i "${inputPath}" -f segment -segment_time 300 -reset_timestamps 1 -map 0 -c copy "${outputFolder}/part_%d.mp4"`;
        execSync(command);
        console.log('✅ ဗီဒီယို ပိုင်းဖြတ်ခြင်း ပြီးဆုံးပါပြီ။');
    } catch (err) {
        console.error('❌ FFmpeg Error:', err);
        throw err;
    }
}

// ၃။ အဓိက Run မယ့် Bot Function
async function startBot() {
    console.log("🚀 GitHub Bot စတင် အလုပ်လုပ်နေပါပြီ...");
    
    try {
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
            
            const tempVideoPath = path.join(__dirname, `temp_${taskId}.mp4`);
            const outputFolder = path.join(__dirname, `parts_${taskId}`);

            console.log(`🎬 Processing Task: ${taskId}`);

            // အဆင့် (က) - YouTube မှ ဗီဒီယို ဒေါင်းလုဒ်ဆွဲခြင်း (npx သုံးပြီး Linux မှာ ဒေါင်းမယ်)
            console.log("⏳ ဗီဒီယို ဒေါင်းလုဒ်ဆွဲနေသည်...");
            try {
                // yt-dlp ကို command တိုက်ရိုက်သုံးပြီး ဒေါင်းခိုင်းတာပါ
                execSync(`npx yt-dlp-exec "${videoUrl}" -o "${tempVideoPath}" -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" --no-check-certificates`);
                console.log("✅ ဒေါင်းလုဒ်ဆွဲခြင်း အောင်မြင်ပါသည်။");
            } catch (dlError) {
                console.error("❌ Download Error:", dlError.message);
                continue; // ဒီ task မရရင် နောက်တစ်ခုကို ကျော်သွားမယ်
            }

            // အဆင့် (ခ) - ဗီဒီယိုကို ၅ မိနစ်စီ ပိုင်းဖြတ်ခြင်း
            await splitVideo(tempVideoPath, outputFolder);

            // အဆင့် (ဂ) - ရလာတဲ့ အပိုင်းတွေကို စစ်ဆေးခြင်း
            const files = fs.readdirSync(outputFolder).filter(f => f.endsWith('.mp4'));
            console.log(`📦 အပိုင်းပေါင်း ${files.length} ပိုင်း ထွက်လာပါပြီ။`);

            // အဆင့် (ဃ) - Firestore မှာ Task ပြီးကြောင်း မှတ်တမ်းတင်ခြင်း
            await tasksRef.doc(doc.id).update({ 
                status: 'completed',
                totalParts: files.length,
                processedAt: admin.firestore.FieldValue.serverTimestamp()
            });

            // ဒေါင်းထားတဲ့ မူရင်းဖိုင်ကြီးကို ပြန်ဖျက်မယ်
            if (fs.existsSync(tempVideoPath)) fs.unlinkSync(tempVideoPath);
            
            console.log(`✅ Task ${taskId} ပြီးမြောက်သွားပါပြီ။`);
        }

    } catch (error) {
        console.error("❌ Bot Error:", error);
    }
}

startBot();
