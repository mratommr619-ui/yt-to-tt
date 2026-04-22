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
    console.error("❌ Firebase Setup Error:", e.message);
    process.exit(1);
}
const db = admin.firestore();

// TikTok Upload Strategy
async function uploadToTikTok(videoPath, movieName, partLabel) {
    const browser = await puppeteer.launch({
        headless: true,
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
    });
    const page = await browser.newPage();
    try {
        let tiktokCookies;
        try {
            tiktokCookies = JSON.parse(process.env.TIKTOK_COOKIES);
        } catch (e) {
            throw new Error("TikTok Cookies JSON format မှားနေပါတယ်");
        }
        await page.setCookie(...tiktokCookies);
        
        console.log(`📤 Uploading to TikTok: ${partLabel}`);
        await page.goto('https://www.tiktok.com/creator-center/upload?from=upload', { waitUntil: 'networkidle2', timeout: 60000 });
        
        const fileInput = await page.waitForSelector('input[type="file"]', { timeout: 30000 });
        await fileInput.uploadFile(videoPath);
        
        console.log("⏳ Waiting for video processing...");
        await new Promise(r => setTimeout(r, 40000)); 

        const fullCaption = `${movieName} (${partLabel}) #foryou #fyp #movie`;
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(fullCaption);

        await new Promise(r => setTimeout(r, 10000));
        await page.click('button[class*="button-post"]');
        console.log(`✅ Success: ${partLabel}`);
    } catch (err) {
        console.error("❌ TikTok Error:", err.message);
    } finally {
        await browser.close();
    }
}

// YouTube Download Strategy
function downloadVideo(url, output) {
    console.log("📥 Downloading video from YouTube...");
    try {
        // Netscape cookies ကို သုံးပြီး အကောင်းဆုံး format ကို ဒေါင်းမယ်
        execSync(`yt-dlp --cookies youtube_cookies.txt "${url}" -o "temp_video.mkv" --no-check-certificate --no-warnings`);
        execSync(`ffmpeg -y -i temp_video.mkv -c:v libx264 -preset ultrafast -crf 28 -c:a aac "${output}"`);
    } catch (e) {
        console.log("⚠️ MKV strategy failed, trying basic format...");
        execSync(`yt-dlp --cookies youtube_cookies.txt "${url}" -o "${output}" -f "b" --no-check-certificate`);
    }
}

async function startBot() {
    let taskSnap = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
    
    if (taskSnap.empty) {
        taskSnap = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
        if (taskSnap.empty) return console.log("💤 Task မရှိသေးပါ။");
        
        const taskDoc = taskSnap.docs[0];
        const { videoUrl } = taskDoc.data();
        
        try {
            downloadVideo(videoUrl, "raw.mp4");
            console.log("✂️ Splitting video into parts...");
            execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
            
            const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
            for (let i = 0; i < files.length; i++) {
                const label = `Part ${i+1}`;
                await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: label, status: 'pending' });
            }
            await taskDoc.ref.update({ status: 'processing' });
        } catch (e) {
            console.error("❌ Download/Split Error:", e.message);
            return;
        }
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

        // Draw text on video
        execSync(`ffmpeg -y -i "part_${fileIndex}.mp4" -vf "drawtext=text='${label}':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=50" "final.mp4"`);
        await uploadToTikTok("final.mp4", movieName || "Review", label);
        await partDoc.ref.update({ status: 'completed' });

        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').count().get();
        if (remain.data().count === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}

startBot();
