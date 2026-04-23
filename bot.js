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

// Universal Downloader
function downloadVideo(url, output) {
    console.log(`📥 Downloading: ${url}`);
    let finalUrl = url;
    if (url.includes('drive.google.com')) {
        const fileId = url.split('/d/')[1]?.split('/')[0] || url.split('id=')[1]?.split('&')[0];
        if (fileId) finalUrl = `https://drive.google.com/uc?export=download&confirm=t&id=${fileId}`;
    }
    try {
        execSync(`yt-dlp --no-check-certificate --user-agent "Mozilla/5.0" "${url}" -o "temp_raw.mp4"`, { stdio: 'inherit' });
    } catch (e) {
        execSync(`curl -L "${finalUrl}" -o "temp_raw.mp4" --user-agent "Mozilla/5.0"`, { stdio: 'inherit' });
    }
    if (fs.existsSync('temp_raw.mp4')) {
        fs.renameSync('temp_raw.mp4', output);
    } else { throw new Error("Download failed."); }
}

// TikTok Upload Logic
async function uploadToTikTok(videoPath, caption) {
    console.log(`📤 Uploading to TikTok: ${caption}`);
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
        await new Promise(r => setTimeout(r, 60000)); 
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(caption);
        await new Promise(r => setTimeout(r, 15000));
        await page.click('button[class*="button-post"]');
        console.log("✅ TikTok Post Completed!");
    } catch (err) {
        console.error("❌ TikTok Error:", err.message);
    } finally {
        await browser.close();
    }
}

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
                await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: label, status: 'pending' });
            }
            await taskDoc.ref.update({ status: 'processing' });
            
            // 🧹 ပထမဆုံးအကြိမ် ခွဲပြီးတာနဲ့ မူရင်း "movie.mp4" ကြီးကို ဖျက်မယ် (နေရာချွေတာဖို့)
            if (fs.existsSync("movie.mp4")) {
                fs.unlinkSync("movie.mp4");
                console.log("🗑️ Original movie file deleted to save space.");
            }

        } catch (e) {
            await taskDoc.ref.update({ status: 'error' });
            return;
        }
    } else {
        const procSnap = await db.collection('tasks').where('status', '==', 'processing').orderBy('createdAt', 'asc').limit(1).get();
        if (procSnap.empty) return console.log("💤 No tasks.");
        taskDoc = procSnap.docs[0];
    }

    const { movieName } = taskDoc.data();
    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex', 'asc').limit(1).get();

    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        const partFile = `part_${fileIndex}.mp4`;

        if (fs.existsSync(partFile)) {
            console.log(`🎬 Processing ${label}...`);
            
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

            // 🧹 တင်ပြီးသွားတဲ့ အပိုင်း (Part) ကို ချက်ချင်းဖျက်မယ်
            if (fs.existsSync(partFile)) fs.unlinkSync(partFile);
            if (fs.existsSync("final.mp4")) fs.unlinkSync("final.mp4");
            console.log(`🗑️ Deleted ${partFile} and final.mp4 after upload.`);
        }

        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').get();
        if (remain.size === 0) {
            await taskDoc.ref.update({ status: 'completed' });
            console.log("🏁 Task fully completed. All files cleaned.");
        }
    }
}
startBot();
