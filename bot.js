const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

// ၁။ Firebase Setup
const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
});
const db = admin.firestore();

// ၂။ TikTok သို့ Video တင်ခြင်း
async function uploadToTikTok(videoPath, movieName, partLabel) {
    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();
    const cookies = JSON.parse(process.env.TIKTOK_COOKIES);
    await page.setCookie(...cookies);

    try {
        await page.goto('https://www.tiktok.com/creator-center/upload?from=upload', { waitUntil: 'networkidle2' });
        const fileInput = await page.$('input[type="file"]');
        await fileInput.uploadFile(videoPath);
        
        await new Promise(r => setTimeout(r, 25000)); // Upload စောင့်ချိန်

        const fullCaption = `${movieName} (${partLabel}) #foryou #fyp #tiktok #movie #review`;
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(fullCaption);

        await new Promise(r => setTimeout(r, 5000));
        await page.click('button[class*="button-post"]');
        console.log(`✅ Uploaded: ${movieName} - ${partLabel}`);
    } catch (err) {
        console.error("❌ Upload Error:", err.message);
    } finally {
        await browser.close();
    }
}

// ၃။ ဗီဒီယိုပေါ် စာသားရေးခြင်း
async function addTextToVideo(inputPath, outputPath, text) {
    const ffmpegCmd = `ffmpeg -i "${inputPath}" -vf "drawtext=text='${text}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=60" -codec:a copy "${outputPath}"`;
    execSync(ffmpegCmd);
}

// ၄။ အဓိက Bot Function (တစ်ခါပွင့် တစ်ပိုင်းတင်စနစ်)
async function startBot() {
    // လက်ရှိ တင်လက်စ ဇာတ်ကားရှိမရှိစစ်မည်
    let taskSnapshot = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
    
    if (taskSnapshot.empty) {
        // အသစ်ဝင်လာသော ဇာတ်ကားကို ယူမည်
        taskSnapshot = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
        if (taskSnapshot.empty) return console.log("💤 No tasks found.");
        
        const taskDoc = taskSnapshot.docs[0];
        const { videoUrl, taskId } = taskDoc.data();
        
        console.log("📥 Downloading and Splitting video...");
        execSync(`npx yt-dlp-exec "${videoUrl}" -o "raw.mp4" -f "mp4"`);
        execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
        
        const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
        for (let i = 0; i < files.length; i++) {
            const label = (i === files.length - 1) ? "END Part" : `Part ${i+1}`;
            await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: label, status: 'pending' });
        }
        await taskDoc.ref.update({ status: 'processing' });
    }

    const taskDoc = taskSnapshot.docs[0];
    const partSnapshot = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();

    if (!partSnapshot.empty) {
        const partDoc = partSnapshot.docs[0];
        const { fileIndex, label } = partDoc.data();
        const { movieName, videoUrl } = taskDoc.data();

        // ဖိုင်မရှိလျှင် ပြန်ဒေါင်း/ဖြတ်မည် (GitHub Actions မှာ ဇာတ်ကားအရှည်ကြီးဆိုရင် လိုအပ်သည်)
        if (!fs.existsSync(`part_${fileIndex}.mp4`)) {
            execSync(`npx yt-dlp-exec "${videoUrl}" -o "raw.mp4" -f "mp4"`);
            execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
        }

        await addTextToVideo(`part_${fileIndex}.mp4`, "final.mp4", label);
        await uploadToTikTok("final.mp4", movieName, label);
        await partDoc.ref.update({ status: 'completed' });

        const remaining = await taskDoc.ref.collection('parts').where('status', '==', 'pending').count().get();
        if (remaining.data().count === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}

startBot();
