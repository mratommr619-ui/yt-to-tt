const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

// ၁။ Firebase Setup
const serviceAccount = require('./serviceAccountKey.json');
admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
});
const db = admin.firestore();

// ၂။ TikTok သို့ Video တင်ခြင်း Function
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
        
        console.log(`📤 Uploading: ${partLabel}...`);
        await new Promise(r => setTimeout(r, 25000)); 

        const fullCaption = `${movieName} (${partLabel}) #foryou #fyp #tiktok #movie #review`;
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(fullCaption);

        await new Promise(r => setTimeout(r, 5000));
        await page.click('button[class*="button-post"]');
        console.log(`✅ Success: ${movieName} - ${partLabel}`);
    } catch (err) {
        console.error("❌ TikTok Error:", err.message);
    } finally {
        await browser.close();
    }
}

// ၃။ ဗီဒီယိုပေါ် စာသားရေးခြင်း
async function addTextToVideo(inputPath, outputPath, text) {
    const ffmpegCmd = `ffmpeg -i "${inputPath}" -vf "drawtext=text='${text}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=60" -codec:a copy "${outputPath}"`;
    try {
        execSync(ffmpegCmd);
    } catch (e) {
        console.error("FFMPEG Error:", e.message);
    }
}

// ၄။ အဓိက Bot Logic
async function startBot() {
    // လက်ရှိ လုပ်နေဆဲ Task ကိုအရင်ရှာမယ်
    let taskSnapshot = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
    
    if (taskSnapshot.empty) {
        // အသစ်ဝင်လာတဲ့ Task ကိုရှာမယ်
        taskSnapshot = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
        if (taskSnapshot.empty) return console.log("💤 No pending tasks.");
        
        const taskDoc = taskSnapshot.docs[0];
        const { videoUrl } = taskDoc.data();
        
        console.log("📥 Downloading & Splitting...");
        execSync(`npx yt-dlp-exec "${videoUrl}" -o "raw.mp4" -f "mp4"`);
        execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
        
        const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
        for (let i = 0; i < files.length; i++) {
            const label = (i === files.length - 1) ? "END Part" : `Part ${i+1}`;
            await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: label, status: 'pending' });
        }
        await taskDoc.ref.update({ status: 'processing' });
        console.log("✅ Task Initialized.");
    }

    const taskDoc = taskSnapshot.docs[0];
    const partSnapshot = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();

    if (!partSnapshot.empty) {
        const partDoc = partSnapshot.docs[0];
        const { fileIndex, label } = partDoc.data();
        const { movieName, videoUrl } = taskDoc.data();

        // GitHub Action အသစ်ပွင့်တိုင်း ဗီဒီယို ပြန်ဒေါင်းရန်လိုအပ် (Free Tier space အတွက်)
        if (!fs.existsSync(`part_${fileIndex}.mp4`)) {
            console.log("🔄 Re-preparing video parts...");
            execSync(`npx yt-dlp-exec "${videoUrl}" -o "raw.mp4" -f "mp4"`);
            execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
        }

        await addTextToVideo(`part_${fileIndex}.mp4`, "final.mp4", label);
        await uploadToTikTok("final.mp4", movieName, label);
        
        await partDoc.ref.update({ status: 'completed' });

        const remaining = await taskDoc.ref.collection('parts').where('status', '==', 'pending').count().get();
        if (remaining.data().count === 0) {
            await taskDoc.ref.update({ status: 'completed' });
            console.log("🏁 All parts uploaded!");
        }
    }
}

startBot();
