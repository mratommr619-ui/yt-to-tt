const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

// Firebase Setup
try {
    const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
    admin.initializeApp({ credential: admin.credential.cert(serviceAccount) });
} catch (e) {
    console.error("Firebase Config Error:", e.message);
    process.exit(1);
}
const db = admin.firestore();

async function uploadToTikTok(videoPath, movieName, partLabel) {
    const browser = await puppeteer.launch({
        headless: true,
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();
    const cookies = JSON.parse(process.env.TIKTOK_COOKIES);
    await page.setCookie(...cookies);

    try {
        await page.goto('https://www.tiktok.com/creator-center/upload?from=upload', { waitUntil: 'networkidle2' });
        const fileInput = await page.$('input[type="file"]');
        await fileInput.uploadFile(videoPath);
        await new Promise(r => setTimeout(r, 25000)); 

        const fullCaption = `${movieName} (${partLabel}) #foryou #fyp #movie`;
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(fullCaption);

        await new Promise(r => setTimeout(r, 5000));
        await page.click('button[class*="button-post"]');
        console.log(`✅ Uploaded: ${partLabel}`);
    } catch (err) {
        console.error("TikTok Error:", err.message);
    } finally {
        await browser.close();
    }
}

async function startBot() {
    let taskSnap = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
    if (taskSnap.empty) {
        taskSnap = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
        if (taskSnap.empty) return console.log("💤 No tasks.");
        
        const taskDoc = taskSnap.docs[0];
        const { videoUrl } = taskDoc.data();
        
        console.log("📥 Downloading & Splitting...");
        execSync(`yt-dlp "${videoUrl}" -o "raw.mp4" -f "mp4"`);
        execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
        
        const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
        for (let i = 0; i < files.length; i++) {
            const label = `Part ${i+1}`;
            await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: label, status: 'pending' });
        }
        await taskDoc.ref.update({ status: 'processing' });
    }

    const taskDoc = taskSnap.docs[0];
    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();

    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        const { movieName, videoUrl } = taskDoc.data();

        if (!fs.existsSync(`part_${fileIndex}.mp4`)) {
            execSync(`yt-dlp "${videoUrl}" -o "raw.mp4" -f "mp4"`);
            execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
        }

        // FFMPEG drawtext စာသားထည့်ခြင်း
        execSync(`ffmpeg -i "part_${fileIndex}.mp4" -vf "drawtext=text='${label}':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=50" "final.mp4"`);
        await uploadToTikTok("final.mp4", movieName || "Trending", label);
        await partDoc.ref.update({ status: 'completed' });

        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').count().get();
        if (remain.data().count === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}

startBot();
