const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

// --- [၁] Firebase Setup ---
try {
    const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
    admin.initializeApp({ credential: admin.credential.cert(serviceAccount) });
} catch (e) {
    console.error("❌ Firebase Auth Error:", e.message);
    process.exit(1);
}
const db = admin.firestore();

// --- [၂] Downloader ---
function downloadVideo(url, output) {
    console.log(`📥 Downloading: ${url}`);
    try {
        execSync(`yt-dlp --no-check-certificate --user-agent "Mozilla/5.0" "${url}" -o "temp_raw.mp4"`, { stdio: 'inherit' });
    } catch (e) {
        // Backup Download for Drive
        let finalUrl = url;
        if (url.includes('drive.google.com')) {
            const fileId = url.split('/d/')[1]?.split('/')[0] || url.split('id=')[1]?.split('&')[0];
            if (fileId) finalUrl = `https://drive.google.com/uc?export=download&confirm=t&id=${fileId}`;
        }
        execSync(`curl -L "${finalUrl}" -o "temp_raw.mp4" --user-agent "Mozilla/5.0"`, { stdio: 'inherit' });
    }
    if (fs.existsSync('temp_raw.mp4')) {
        fs.renameSync('temp_raw.mp4', output);
    } else {
        throw new Error("Download failed.");
    }
}

// --- [၃] Hybrid TikTok Upload (Cookie + Password) ---
async function uploadToTikTok(videoPath, caption) {
    console.log("🚀 Starting TikTok Upload Process...");
    const browser = await puppeteer.launch({
        headless: true,
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1280,720']
    });
    const page = await browser.newPage();

    try {
        // [A] Try Login with Cookies First
        if (process.env.TIKTOK_COOKIES) {
            console.log("🍪 Injecting Cookies...");
            const cookies = JSON.parse(process.env.TIKTOK_COOKIES);
            await page.setCookie(...cookies);
        }

        await page.goto('https://www.tiktok.com/creator-center/upload?from=upload', { waitUntil: 'networkidle2', timeout: 90000 });

        // [B] If redirected to login, use Credentials
        if (page.url().includes('login')) {
            console.log("🔑 Cookies missing/expired. Trying Username/Password...");
            const user = process.env.TIKTOK_USERNAME;
            const pass = process.env.TIKTOK_PASSWORD;
            
            if (!user || !pass) throw new Error("No Login Credentials Found!");

            await page.goto('https://www.tiktok.com/login/phone-or-email/email', { waitUntil: 'networkidle2' });
            await page.type('input[name="username"]', user, { delay: 100 });
            await page.type('input[type="password"]', pass, { delay: 100 });
            await page.click('button[type="submit"]');
            
            console.log("⌛ Waiting for post-login (30s for possible Captcha)...");
            await new Promise(r => setTimeout(r, 30000));
            
            await page.goto('https://www.tiktok.com/creator-center/upload?from=upload', { waitUntil: 'networkidle2' });
        }

        // --- Video Upload Logic ---
        console.log("📤 Uploading File...");
        const fileInput = await page.waitForSelector('input[type="file"]', { timeout: 60000 });
        await fileInput.uploadFile(videoPath);
        
        console.log("⌛ Processing (60s)...");
        await new Promise(r => setTimeout(r, 60000)); 

        // Caption
        console.log("✍️ Setting Caption...");
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(caption);

        await new Promise(r => setTimeout(r, 10000));

        // Post Button
        await page.click('button[class*="button-post"]');
        console.log("✅ TikTok Post Completed!");

    } catch (err) {
        console.error("❌ TikTok Error:", err.message);
        await page.screenshot({ path: 'tiktok_error.png' });
    } finally {
        await browser.close();
    }
}

// --- [၄] Main Logic ---
async function startBot() {
    let taskSnap = await db.collection('tasks').where('status', '==', 'pending').orderBy('createdAt', 'asc').limit(1).get();
    let taskDoc;

    if (!taskSnap.empty) {
        taskDoc = taskSnap.docs[0];
        const { videoUrl } = taskDoc.data();
        try {
            downloadVideo(videoUrl, "movie.mp4");
            
            console.log("✂️ Fast Splitting Video...");
            execSync(`ffmpeg -i "movie.mp4" -c copy -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
            
            const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
            for (let i = 0; i < files.length; i++) {
                const label = (i === files.length - 1) ? "End Part" : `Part - ${i+1}`;
                await taskDoc.ref.collection('parts').doc(`p${i}`).set({ 
                    fileIndex: i, label: label, status: 'pending' 
                });
            }
            await taskDoc.ref.update({ status: 'processing' });
            if (fs.existsSync("movie.mp4")) fs.unlinkSync("movie.mp4");
        } catch (e) {
            await taskDoc.ref.update({ status: 'error' });
            return;
        }
    } else {
        const procSnap = await db.collection('tasks').where('status', '==', 'processing').orderBy('createdAt', 'asc').limit(1).get();
        if (procSnap.empty) return console.log("💤 No active tasks.");
        taskDoc = procSnap.docs[0];
    }

    const { movieName } = taskDoc.data();
    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex', 'asc').limit(1).get();

    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        const partFile = `part_${fileIndex}.mp4`;

        if (fs.existsSync(partFile)) {
            console.log(`🎬 Editing ${label}...`);
            
            const watermark = "@juneking619";
            const xPos = "(w-text_w)/2 + ((w-text_w)/2)*sin(2*PI*t/30)";
            const yPos = "(h-text_h)/2 + ((h-text_h)/2)*cos(2*PI*t/20)";
            
            const floatingW = `drawtext=text='${watermark}':fontcolor=yellow@0.4:fontsize=35:x='${xPos}':y='${yPos}':shadowcolor=black:shadowx=2:shadowy=2`;
            const labelStyle = `drawtext=text='${label}':fontcolor=white:fontsize=85:font='Sans':borderw=4:bordercolor=red:x=(w-text_w)/2:y=(h-text_h)/2-100:enable='between(t,0,3)'`;
            const movieLabel = `drawtext=text='${movieName}':fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=h-80`;

            execSync(`ffmpeg -y -i "${partFile}" -vf "${labelStyle},${movieLabel},${floatingW}" "final.mp4"`);
            
            const caption = `${movieName} - ${label} #foryou #fyp #tiktok @juneking619`;
            await uploadToTikTok("final.mp4", caption);
            
            await partDoc.ref.update({ status: 'completed' });
            
            // 🧹 Clean up
            if (fs.existsSync(partFile)) fs.unlinkSync(partFile);
            if (fs.existsSync("final.mp4")) fs.unlinkSync("final.mp4");
        }

        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').get();
        if (remain.size === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}

startBot();
