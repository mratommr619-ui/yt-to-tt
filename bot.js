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
    process.exit(1);
}
const db = admin.firestore();

// 🔥 Universal Downloader (Bypass Strategy)
function downloadVideo(url, output) {
    console.log(`📥 Downloading from: ${url}`);
    
    // Google Drive Link ကို Direct Link အဖြစ် အလိုအလျောက် ပြောင်းခြင်း
    let finalUrl = url;
    if (url.includes('drive.google.com')) {
        const fileId = url.split('/d/')[1]?.split('/')[0] || url.split('id=')[1]?.split('&')[0];
        if (fileId) {
            finalUrl = `https://drive.google.com/uc?export=download&id=${fileId}`;
            console.log(`🔄 Drive Direct Link converted: ${finalUrl}`);
        }
    }

    try {
        // Strategy 1: CURL နဲ့ တိုက်ရိုက်ဆွဲခြင်း (Direct Links & Drive)
        console.log("Strategy 1: Attempting direct CURL download...");
        execSync(`curl -L "${finalUrl}" -o "temp_raw.mp4" --user-agent "Mozilla/5.0" --max-time 300`, { stdio: 'inherit' });
        
        if (fs.existsSync('temp_raw.mp4') && fs.statSync('temp_raw.mp4').size > 100000) { // အနည်းဆုံး 100KB ရှိမှ
            console.log("✅ Strategy 1 Success!");
        } else {
            throw new Error("File too small, trying next strategy.");
        }
    } catch (e) {
        try {
            // Strategy 2: yt-dlp နဲ့ ဒေါင်းခြင်း (Facebook, TikTok, Others)
            console.log("Strategy 2: Attempting yt-dlp download...");
            execSync(`yt-dlp --no-check-certificate --user-agent "Mozilla/5.0" "${url}" -o "temp_raw.mp4" --no-warnings`, { stdio: 'inherit' });
        } catch (e2) {
            // Strategy 3: YouTube Proxy Bypass (YouTube links only)
            if (url.includes('youtube.com') || url.includes('youtu.be')) {
                console.log("Strategy 3: Attempting YouTube Proxy Bypass...");
                const videoId = url.split('v=')[1]?.split('&')[0] || url.split('/').pop().split('?')[0];
                const proxyUrl = `https://yewtu.be/latest_version?id=${videoId}&itag=22`;
                execSync(`curl -L "${proxyUrl}" -o "temp_raw.mp4" --user-agent "Mozilla/5.0"`, { stdio: 'inherit' });
            } else {
                throw new Error("All download strategies failed.");
            }
        }
    }

    if (fs.existsSync('temp_raw.mp4')) {
        console.log("⚙️ Re-encoding video for TikTok compatibility...");
        execSync(`ffmpeg -y -i temp_raw.mp4 -c:v libx264 -preset ultrafast -crf 28 -c:a aac "${output}"`);
    } else {
        throw new Error("Download failed - No file generated.");
    }
}

// TikTok Upload Part
async function uploadToTikTok(videoPath, caption) {
    console.log("📤 Uploading to TikTok...");
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
        
        console.log("⌛ Video is processing (60s)...");
        await new Promise(r => setTimeout(r, 60000)); 

        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(caption);

        await new Promise(r => setTimeout(r, 15000));
        await page.click('button[class*="button-post"]');
        console.log(`✅ Success: ${caption}`);
    } catch (err) {
        console.error("❌ TikTok Error:", err.message);
    } finally {
        await browser.close();
    }
}

async function startBot() {
    // Check pending tasks
    let taskSnap = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
    let taskDoc;

    if (!taskSnap.empty) {
        taskDoc = taskSnap.docs[0];
        const { videoUrl } = taskDoc.data();
        try {
            downloadVideo(videoUrl, "raw.mp4");
            console.log("✂️ Splitting into 5-min parts...");
            execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
            
            const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
            for (let i = 0; i < files.length; i++) {
                const label = (i === files.length - 1) ? "End Part" : `Part ${i+1}`;
                await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: label, status: 'pending' });
            }
            await taskDoc.ref.update({ status: 'processing' });
        } catch (e) {
            console.error(e.message);
            await taskDoc.ref.update({ status: 'error' });
            return;
        }
    } else {
        // Continue processing existing task
        const procSnap = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
        if (procSnap.empty) return console.log("💤 No tasks.");
        taskDoc = procSnap.docs[0];
    }

    const { movieName } = taskDoc.data();
    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();

    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        const partFile = `part_${fileIndex}.mp4`;

        if (fs.existsSync(partFile)) {
            execSync(`ffmpeg -y -i "${partFile}" -vf "drawtext=text='${label}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=80" "final.mp4"`);
            await uploadToTikTok("final.mp4", `${movieName} - ${label} #foryou #fyp #movie`);
            await partDoc.ref.update({ status: 'completed' });
        }

        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').get();
        if (remain.size === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}
startBot();
