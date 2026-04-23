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
    console.error("Firebase Key Error");
    process.exit(1);
}
const db = admin.firestore();

// 🔥 Universal Downloader - ဘယ် Link မဆို ဒေါင်းမည့်စနစ်
function downloadVideo(url, output) {
    console.log(`📥 Downloading from: ${url}`);
    try {
        // --no-check-certificate: SSL error တွေကျော်ဖို့
        // --user-agent: Browser အစစ်လို အယောင်ဆောင်ဖို့
        // --geo-bypass: နိုင်ငံကန့်သတ်ချက်ကျော်ဖို့
        const command = `yt-dlp --no-check-certificate --user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36" --geo-bypass --add-header "Referer:https://www.google.com/" "${url}" -o "temp_raw.mp4"`;
        
        execSync(command, { stdio: 'inherit' });

        if (fs.existsSync('temp_raw.mp4')) {
            // ဗီဒီယိုကို Standard MP4 (H.264) ဖြစ်အောင် FFmpeg နဲ့ ပြန်ပြောင်းမယ်
            console.log("⚙️ Converting/Processing Video...");
            execSync(`ffmpeg -y -i temp_raw.mp4 -c:v libx264 -preset ultrafast -crf 28 -c:a aac "${output}"`);
            console.log("✅ Download Successful!");
        } else {
            throw new Error("File not found after download attempt.");
        }
    } catch (e) {
        console.error("❌ Download Failed:", e.message);
        throw new Error("ဗီဒီယို ဒေါင်းလုဒ်မရပါ။ Link သေနေခြင်း (သို့) ပိတ်ထားခြင်း ဖြစ်နိုင်ပါတယ်။");
    }
}

// TikTok Upload Logic (မပြောင်းလဲပါ)
async function uploadToTikTok(videoPath, caption) {
    console.log(`📤 Uploading to TikTok: ${caption}`);
    const browser = await puppeteer.launch({
        headless: true,
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
    });
    const page = await browser.newPage();
    try {
        const cookies = JSON.parse(process.env.TIKTOK_COOKIES);
        await page.setCookie(...cookies);
        await page.goto('https://www.tiktok.com/creator-center/upload?from=upload', { waitUntil: 'networkidle2' });
        
        const fileInput = await page.waitForSelector('input[type="file"]');
        await fileInput.uploadFile(videoPath);
        
        console.log("⌛ Waiting for upload and processing (60s)...");
        await new Promise(r => setTimeout(r, 60000)); 

        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(caption);

        await new Promise(r => setTimeout(r, 15000));
        await page.click('button[class*="button-post"]');
        console.log("✅ TikTok Post Successful!");
    } catch (err) {
        console.error("❌ TikTok Error:", err.message);
    } finally {
        await browser.close();
    }
}

async function startBot() {
    // 1. Pending Task ရှိမရှိ အရင်ကြည့်မယ်
    let taskSnap = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
    let taskDoc;

    if (!taskSnap.empty) {
        taskDoc = taskSnap.docs[0];
        const { videoUrl } = taskDoc.data();
        try {
            downloadVideo(videoUrl, "raw.mp4");
            console.log("✂️ Splitting video into 5-minute segments...");
            execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
            
            const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
            for (let i = 0; i < files.length; i++) {
                const label = (i === files.length - 1) ? "The End" : `Part ${i+1}`;
                await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: label, status: 'pending' });
            }
            await taskDoc.ref.update({ status: 'processing' });
        } catch (e) {
            await taskDoc.ref.update({ status: 'error' });
            return;
        }
    } else {
        // 2. Processing ဖြစ်နေတဲ့ Task ထဲက ကျန်တဲ့ Part တွေကို တင်မယ်
        const processingSnap = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
        if (processingSnap.empty) return console.log("💤 No tasks to work on.");
        taskDoc = processingSnap.docs[0];
    }

    const { movieName } = taskDoc.data();
    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();

    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        const partFile = `part_${fileIndex}.mp4`;

        if (fs.existsSync(partFile)) {
            // Label စာသားထည့်မယ်
            execSync(`ffmpeg -y -i "${partFile}" -vf "drawtext=text='${label}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=80" "final.mp4"`);
            await uploadToTikTok("final.mp4", `${movieName} - ${label} #movie #foryou #fyp`);
            await partDoc.ref.update({ status: 'completed' });
        }

        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').get();
        if (remain.size === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}
startBot();
