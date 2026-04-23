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

function downloadVideo(url, output) {
    console.log(`📥 Processing URL: ${url}`);
    
    // YouTube Link ကို Proxy (Invidious) Link အဖြစ် ပြောင်းလဲခြင်း
    // ဒါမှ YouTube က GitHub ရဲ့ IP ကို မသိမှာပါ
    let proxyUrl = url;
    if (url.includes('youtube.com') || url.includes('youtu.be')) {
        console.log("🔄 YouTube link detected. Converting to Proxy for bypass...");
        const videoId = url.split('v=')[1]?.split('&')[0] || url.split('/').pop().split('?')[0];
        proxyUrl = `https://yewtu.be/latest_version?id=${videoId}&itag=22`; 
        // itag 22 ဆိုတာ 720p mp4 ကို ပြောတာပါ
    }

    try {
        console.log(`🚀 Downloading from Proxy: ${proxyUrl}`);
        // Proxy ကနေ တိုက်ရိုက်ဆွဲချမယ် (Cookie မလိုတော့ဘူး)
        execSync(`curl -L "${proxyUrl}" -o "temp_raw.mp4" --user-agent "Mozilla/5.0"`);
        
        if (!fs.existsSync('temp_raw.mp4') || fs.statSync('temp_raw.mp4').size < 1000) {
            throw new Error("Proxy download failed or file empty.");
        }

        execSync(`ffmpeg -y -i temp_raw.mp4 -c:v libx264 -preset ultrafast -crf 28 -c:a aac "${output}"`);
        console.log("✅ Bypass Download Successful!");
    } catch (e) {
        console.log("⚠️ Proxy failed. Trying fallback standard download...");
        try {
            execSync(`yt-dlp --no-check-certificate "${url}" -o "temp_raw.mp4" --no-warnings`);
            execSync(`ffmpeg -y -i temp_raw.mp4 -c:v libx264 -preset ultrafast -crf 28 -c:a aac "${output}"`);
        } catch (fallbackError) {
            throw new Error("YouTube blocks everything. Try a different video or Facebook link.");
        }
    }
}

// TikTok Upload Part (မပြောင်းလဲပါ)
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
        await new Promise(r => setTimeout(r, 60000)); 
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(caption);
        await new Promise(r => setTimeout(r, 15000));
        await page.click('button[class*="button-post"]');
        console.log(`✅ Posted to TikTok: ${caption}`);
    } catch (err) {
        console.error("❌ TikTok Error:", err.message);
    } finally {
        await browser.close();
    }
}

async function startBot() {
    // Firestore ကနေ pending task ယူမယ်
    const taskSnap = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
    let taskDoc;

    if (!taskSnap.empty) {
        taskDoc = taskSnap.docs[0];
        const { videoUrl, movieName } = taskDoc.data();
        try {
            downloadVideo(videoUrl, "raw.mp4");
            console.log("✂️ Splitting into 5-minute parts...");
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
    } else {
        // processing ဖြစ်နေတဲ့ task ရှိလား ထပ်စစ်မယ်
        const processingSnap = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
        if (processingSnap.empty) return console.log("💤 Task မရှိပါ။");
        taskDoc = processingSnap.docs[0];
    }

    // တင်ဖို့ကျန်နေတဲ့ အပိုင်း (Part) ကို ရှာမယ်
    const { movieName } = taskDoc.data();
    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();

    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        if (fs.existsSync(`part_${fileIndex}.mp4`)) {
            execSync(`ffmpeg -y -i "part_${fileIndex}.mp4" -vf "drawtext=text='${label}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=80" "final.mp4"`);
            await uploadToTikTok("final.mp4", `${movieName} - ${label} #foryou #fyp #movie`);
            await partDoc.ref.update({ status: 'completed' });
        }
        
        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').get();
        if (remain.size === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}
startBot();
