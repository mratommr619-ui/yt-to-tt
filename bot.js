const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

// 🔥 Firebase Setup (GitHub Secret မှ ဖတ်ရန် ပြင်ဆင်မှု)
try {
    const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
    admin.initializeApp({
        credential: admin.credential.cert(serviceAccount)
    });
} catch (error) {
    console.error("❌ Firebase Initialization Error:", error.message);
    process.exit(1);
}

const db = admin.firestore();

// ... (uploadToTikTok နှင့် addTextToVideo function များက အရင်အတိုင်းပါပဲ) ...
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
        await new Promise(r => setTimeout(r, 25000)); 

        const fullCaption = `${movieName} (${partLabel}) #foryou #fyp #tiktok #movie`;
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

async function addTextToVideo(inputPath, outputPath, text) {
    const ffmpegCmd = `ffmpeg -i "${inputPath}" -vf "drawtext=text='${text}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=60" -codec:a copy "${outputPath}"`;
    execSync(ffmpegCmd);
}

// 🚀 Main Bot Logic
async function startBot() {
    let taskSnapshot = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
    
    if (taskSnapshot.empty) {
        taskSnapshot = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
        if (taskSnapshot.empty) return console.log("💤 No tasks found.");
        
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
    }

    const taskDoc = taskSnapshot.docs[0];
    const partSnapshot = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();

    if (!partSnapshot.empty) {
        const partDoc = partSnapshot.docs[0];
        const { fileIndex, label } = partDoc.data();
        const { movieName, videoUrl } = taskDoc.data();

        if (!fs.existsSync(`part_${fileIndex}.mp4`)) {
            execSync(`npx yt-dlp-exec "${videoUrl}" -o "raw.mp4" -f "mp4"`);
            execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
        }

        await addTextToVideo(`part_${fileIndex}.mp4`, "final.mp4", label);
        await uploadToTikTok("final.mp4", movieName || "Trending Movie", label);
        await partDoc.ref.update({ status: 'completed' });

        const remaining = await taskDoc.ref.collection('parts').where('status', '==', 'pending').count().get();
        if (remaining.data().count === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}

startBot();
