const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

// Firebase Initialization
try {
    const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
    admin.initializeApp({ credential: admin.credential.cert(serviceAccount) });
} catch (e) {
    console.error("Firebase Error:", e.message);
    process.exit(1);
}
const db = admin.firestore();

// TikTok Upload Function
async function uploadToTikTok(videoPath, movieName, partLabel) {
    const browser = await puppeteer.launch({
        headless: true,
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();
    try {
        const cookies = JSON.parse(process.env.TIKTOK_COOKIES);
        await page.setCookie(...cookies);
        
        await page.goto('https://www.tiktok.com/creator-center/upload?from=upload', { waitUntil: 'networkidle2' });
        const fileInput = await page.$('input[type="file"]');
        await fileInput.uploadFile(videoPath);
        
        await new Promise(r => setTimeout(r, 30000)); // ဗီဒီယို တက်အောင် စောင့်မယ်

        const fullCaption = `${movieName} (${partLabel}) #foryou #fyp #movie`;
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(fullCaption);

        await new Promise(r => setTimeout(r, 10000));
        await page.click('button[class*="button-post"]');
        console.log(`✅ Upload Success: ${partLabel}`);
    } catch (err) {
        console.error("TikTok Error:", err.message);
    } finally {
        await browser.close();
    }
}

// YouTube Download Logic
function downloadVideo(url, output) {
    console.log("📥 Downloading with bypass strategy...");
    try {
        // အရင်ဆုံး format မရွေးဘဲ အကောင်းဆုံးကို ဒေါင်းပြီး mkv ထုတ်မယ်
        execSync(`yt-dlp --cookies youtube_cookies.txt "${url}" -o "temp_video.mkv" --format "bestvideo+bestaudio/best" --merge-output-format mkv --no-check-certificates`);
        // ဒေါင်းပြီးသားကို standard mp4 ပြန်ပြောင်းမယ် (ဖြတ်ရလွယ်အောင်)
        execSync(`ffmpeg -y -i temp_video.mkv -c:v libx264 -preset fast -crf 23 -c:a aac "${output}"`);
    } catch (e) {
        console.log("⚠️ MKV download failed, trying simple MP4...");
        execSync(`yt-dlp --cookies youtube_cookies.txt "${url}" -o "${output}" -f "best" --no-check-certificates`);
    }
}

async function startBot() {
    let taskSnap = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
    
    if (taskSnap.empty) {
        taskSnap = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
        if (taskSnap.empty) return console.log("💤 No pending tasks.");
        
        const taskDoc = taskSnap.docs[0];
        const { videoUrl } = taskDoc.data();
        
        downloadVideo(videoUrl, "raw.mp4");
        
        console.log("✂️ Splitting into parts...");
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
            downloadVideo(videoUrl, "raw.mp4");
            execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
        }

        // စာသားထည့်မယ်
        execSync(`ffmpeg -y -i "part_${fileIndex}.mp4" -vf "drawtext=text='${label}':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=50" "final.mp4"`);
        await uploadToTikTok("final.mp4", movieName || "Review", label);
        await partDoc.ref.update({ status: 'completed' });

        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').count().get();
        if (remain.data().count === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}

startBot();
