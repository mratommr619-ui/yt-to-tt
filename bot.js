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
} catch (e) { process.exit(1); }
const db = admin.firestore();

// --- [၂] Downloader ---
function downloadVideo(url, output) {
    console.log("🔄 Updating yt-dlp...");
    try { execSync(`pip install -U yt-dlp`, { stdio: 'inherit' }); } catch (e) {}
    console.log(`📥 Downloading: ${url}`);
    try {
        execSync(`yt-dlp --no-check-certificate --user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" "${url}" -o "temp_raw.mp4"`, { stdio: 'inherit' });
    } catch (e) {
        execSync(`curl -L "${url}" -o "temp_raw.mp4" --user-agent "Mozilla/5.0"`, { stdio: 'inherit' });
    }
    if (fs.existsSync('temp_raw.mp4')) fs.renameSync('temp_raw.mp4', output);
}

// --- [၃] Enhanced Stealth TikTok Upload ---
async function uploadToTikTok(videoPath, caption) {
    console.log("🚀 Starting Stealth Upload...");
    const browser = await puppeteer.launch({
        headless: "new", // Headless mode အသစ်ကိုသုံးမယ်
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH,
        args: [
            '--no-sandbox', 
            '--disable-setuid-sandbox', 
            '--disable-blink-features=AutomationControlled', // Bot မှန်းမသိအောင်
            '--window-size=1920,1080'
        ]
    });
    const page = await browser.newPage();
    
    // Webdriver လို့ မပေါ်အောင် ဖုံးကွယ်မယ်
    await page.evaluateOnNewDocument(() => {
        Object.defineProperty(navigator, 'webdriver', { get: () => false });
    });

    try {
        if (process.env.TIKTOK_COOKIES) {
            const cookies = JSON.parse(process.env.TIKTOK_COOKIES);
            await page.setCookie(...cookies);
        }

        await page.goto('https://www.tiktok.com/creator-center/upload?from=upload', { waitUntil: 'networkidle2', timeout: 120000 });

        // တကယ်လို့ Login ပြန်တောင်းရင်
        if (page.url().includes('login')) {
            console.log("🔑 Login Session Expired. Please Update Cookies for better results!");
            return; // Cookie မရှိရင် Password နဲ့ဝင်တာက Captcha မိဖို့ အရမ်းများပါတယ်
        }

        console.log("📤 Uploading File...");
        const fileInput = await page.waitForSelector('input[type="file"]');
        await fileInput.uploadFile(videoPath);
        
        // Processing ကို အကြာကြီးစောင့်မယ် (၅ မိနစ်စာမို့လို့)
        console.log("⌛ Video Processing (90s)...");
        await new Promise(r => setTimeout(r, 90000)); 

        console.log("✍️ Typing Caption...");
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        // လူရိုက်သလို ဖြည်းဖြည်းချင်း ရိုက်မယ်
        for (const char of caption) {
            await page.keyboard.sendCharacter(char);
            await new Promise(r => setTimeout(r, 50));
        }
        await new Promise(r => setTimeout(r, 5000));

        console.log("🚀 Clicking Post Button...");
        // Post ခလုတ်ပေါ် Mouse ကို အရင်ရွှေ့မယ် (Stealth)
        const postBtnSelector = 'button:has-text("Post"), button:contains("Post")'; 
        
        await page.evaluate(() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const postBtn = btns.find(b => b.innerText.includes('Post') || b.textContent.includes('Post'));
            if (postBtn) {
                postBtn.scrollIntoView();
                // စက်ရုပ်မဟုတ်ကြောင်းပြဖို့ ခလုတ်ကို မနှိပ်ခင် ခဏစောင့်မယ်
                setTimeout(() => postBtn.click(), 2000);
            } else {
                throw new Error("Post button not found");
            }
        });

        // 🔥 အရေးကြီးဆုံး: တကယ်တင်ပြီးကြောင်း "Manage your posts" စာသားပေါ်လာမှ Success ပြမယ်
        console.log("⌛ Verifying Upload Success...");
        await page.waitForFunction(
            () => document.body.innerText.includes("Manage your posts") || 
                  document.body.innerText.includes("View profile"),
            { timeout: 90000 }
        );
        console.log("✅ TikTok confirmed the post is LIVE!");

    } catch (err) {
        console.error("❌ TikTok Error:", err.message);
        await page.screenshot({ path: 'tiktok_error.png' });
        throw err; 
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
        try {
            downloadVideo(taskDoc.data().videoUrl, "movie.mp4");
            execSync(`ffmpeg -i "movie.mp4" -c copy -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);
            const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
            for (let i = 0; i < files.length; i++) {
                const label = (i === files.length - 1) ? "End Part" : `Part - ${i+1}`;
                await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: label, status: 'pending' });
            }
            await taskDoc.ref.update({ status: 'processing' });
            if (fs.existsSync("movie.mp4")) fs.unlinkSync("movie.mp4");
        } catch (e) { await taskDoc.ref.update({ status: 'error' }); return; }
    } else {
        const procSnap = await db.collection('tasks').where('status', '==', 'processing').orderBy('createdAt', 'asc').limit(1).get();
        if (procSnap.empty) return;
        taskDoc = procSnap.docs[0];
    }

    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex', 'asc').limit(1).get();
    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        const partFile = `part_${fileIndex}.mp4`;
        if (fs.existsSync(partFile)) {
            try {
                console.log(`🎬 Processing ${label}...`);
                const movieName = taskDoc.data().movieName;
                const watermark = "@juneking619";
                const xPos = "(w-text_w)/2 + ((w-text_w)/2)*sin(2*PI*t/30)";
                const yPos = "(h-text_h)/2 + ((h-text_h)/2)*cos(2*PI*t/20)";
                const floatingW = `drawtext=text='${watermark}':fontcolor=yellow@0.4:fontsize=35:x='${xPos}':y='${yPos}':shadowcolor=black:shadowx=2:shadowy=2`;
                const labelStyle = `drawtext=text='${label}':fontcolor=white:fontsize=85:font='Sans':borderw=4:bordercolor=red:x=(w-text_w)/2:y=(h-text_h)/2-100:enable='between(t,0,3)'`;
                const movieLabel = `drawtext=text='${movieName}':fontcolor=white@0.7:fontsize=40:x=(w-text_w)/2:y=h-80`;

                execSync(`ffmpeg -y -i "${partFile}" -vf "${labelStyle},${movieLabel},${floatingW}" "final.mp4"`);
                
                await uploadToTikTok("final.mp4", `${movieName} - ${label} ${taskDoc.data().hashtags || "#fyp"}`);
                await partDoc.ref.update({ status: 'completed' }); 
            } catch (err) {
                console.log("❌ Part upload failed - will retry next time.");
            }
            if (fs.existsSync(partFile)) fs.unlinkSync(partFile);
            if (fs.existsSync("final.mp4")) fs.unlinkSync("final.mp4");
        }
        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').get();
        if (remain.size === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}
startBot();
