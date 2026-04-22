const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

try {
    const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
    admin.initializeApp({ credential: admin.credential.cert(serviceAccount) });
} catch (e) {
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
    try {
        const cookies = JSON.parse(process.env.TIKTOK_COOKIES);
        await page.setCookie(...cookies);
        await page.goto('https://www.tiktok.com/creator-center/upload?from=upload', { waitUntil: 'networkidle2' });
        const fileInput = await page.waitForSelector('input[type="file"]');
        await fileInput.uploadFile(videoPath);
        await new Promise(r => setTimeout(r, 40000)); 
        const fullCaption = `${movieName} (${partLabel}) #foryou #fyp #movie`;
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(fullCaption);
        await new Promise(r => setTimeout(r, 10000));
        await page.click('button[class*="button-post"]');
        console.log(`✅ Upload Success: ${partLabel}`);
    } catch (err) {
        console.error("❌ TikTok Error:", err.message);
    } finally {
        await browser.close();
    }
}

function downloadVideo(url, output) {
    console.log("📥 Attempting Download with Browser Bypass...");
    const userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
    try {
        // User Agent နဲ့ Cookie ကို ပေါင်းသုံးပြီး အစွမ်းကုန် ကျော်မယ်
        execSync(`yt-dlp --cookies youtube_cookies.txt --user-agent "${userAgent}" "${url}" -o "temp.mkv" --no-check-certificate --no-warnings`);
        execSync(`ffmpeg -y -i temp.mkv -c:v libx264 -preset fast -crf 26 -c:a aac "${output}"`);
    } catch (e) {
        console.log("⚠️ Failed! Trying Mobile Bypass...");
        const mobileUA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1";
        execSync(`yt-dlp --cookies youtube_cookies.txt --user-agent "${mobileUA}" "${url}" -o "${output}" -f "b" --no-check-certificate`);
    }
}

async function startBot() {
    let taskSnap = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
    if (taskSnap.empty) {
        taskSnap = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
        if (taskSnap.empty) return console.log("💤 No tasks.");
        const taskDoc = taskSnap.docs[0];
        const { videoUrl } = taskDoc.data();
        try {
            downloadVideo(videoUrl, "raw.mp4");
            execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
            const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
            for (let i = 0; i < files.length; i++) {
                await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: `Part ${i+1}`, status: 'pending' });
            }
            await taskDoc.ref.update({ status: 'processing' });
        } catch (e) { console.error(e.message); return; }
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
        execSync(`ffmpeg -y -i "part_${fileIndex}.mp4" -vf "drawtext=text='${label}':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=50" "final.mp4"`);
        await uploadToTikTok("final.mp4", movieName, label);
        await partDoc.ref.update({ status: 'completed' });
        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').count().get();
        if (remain.data().count === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}
startBot();
