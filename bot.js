const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

try {
    const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
    admin.initializeApp({ credential: admin.credential.cert(serviceAccount) });
} catch (e) { process.exit(1); }
const db = admin.firestore();

// 🔥 YouTube Bypass Downloader (External API)
function downloadVideo(url, output) {
    console.log("📥 External API သုံးပြီး YouTube ကို Bypass လုပ်နေပါသည်...");
    try {
        // Cobalt လိုမျိုး public API တစ်ခုခုကို သုံးပြီး ဒေါင်းဖို့ ကြိုးစားမယ်
        // GitHub IP ကို ကျော်ဖို့ ဒါက အကောင်းဆုံးပဲ
        execSync(`yt-dlp --no-check-certificate --user-agent "Mozilla/5.0" --geo-bypass --force-overwrites "${url}" -o "temp_raw.mp4"`);
    } catch (e) {
        console.log("Strategy 1 failed. Trying Strategy 2...");
        try {
             // တကယ်လို့ ပုံမှန်မရရင် အောက်ကနည်းနဲ့ အတင်းဆွဲမယ်
             execSync(`yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" --no-check-certificate "${url}" -o "temp_raw.mp4"`);
        } catch (e2) {
            throw new Error("YouTube blocks everything. Please use a Facebook or Drive link.");
        }
    }

    if (fs.existsSync('temp_raw.mp4')) {
        execSync(`ffmpeg -y -i temp_raw.mp4 -c:v libx264 -preset ultrafast -crf 28 -c:a aac "${output}"`);
        console.log("✅ Download Successful!");
    } else {
        throw new Error("Download Failed.");
    }
}

// TikTok Upload Logic
async function uploadToTikTok(videoPath, caption) {
    console.log("📤 TikTok တင်နေပါသည်...");
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
        await new Promise(r => setTimeout(r, 60000)); // ဗီဒီယိုကြီးရင် စောင့်ချိန်တိုးပေးထားတယ်
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
    let taskSnap = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
    if (taskSnap.empty) {
        taskSnap = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
        if (taskSnap.empty) return console.log("💤 No tasks.");
    }

    const taskDoc = taskSnap.docs[0];
    const { videoUrl, movieName, status } = taskDoc.data();

    if (status === 'pending') {
        try {
            downloadVideo(videoUrl, "raw.mp4");
            console.log("✂️ Splitting video...");
            execSync(`ffmpeg -i "raw.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
            const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
            for (let i = 0; i < files.length; i++) {
                const label = (i === files.length - 1) ? "End Part" : `Part ${i+1}`;
                await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: label, status: 'pending' });
            }
            await taskDoc.ref.update({ status: 'processing' });
        } catch (e) {
            await taskDoc.ref.update({ status: 'error' });
            return;
        }
    }

    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();
    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        execSync(`ffmpeg -y -i "part_${fileIndex}.mp4" -vf "drawtext=text='${label}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=80" "final.mp4"`);
        await uploadToTikTok("final.mp4", `${movieName} - ${label} #foryou #fyp #tiktok`);
        await partDoc.ref.update({ status: 'completed' });
        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').get();
        if (remain.size === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}
startBot();
