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
    console.log(`📥 YouTube Video ကို Cookies သုံးပြီး ဒေါင်းနေပါသည်...`);
    try {
        // cookies.txt ကို သေချာဖတ်ပြီး yt-dlp ကို ပေးမယ်
        // --cookies-from-browser က GitHub မှာ အလုပ်မလုပ်လို့ --cookies နဲ့ပဲ သွားမယ်
        const command = `yt-dlp --cookies youtube_cookies.txt --no-check-certificate --format "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" "${url}" -o "temp_raw.mp4"`;
        
        execSync(command, { stdio: 'inherit' });

        if (fs.existsSync('temp_raw.mp4')) {
            // ffmpeg နဲ့ ပြန်ပြီး standard ဖြစ်အောင် လုပ်မယ် (ဖြတ်တဲ့အခါ error မတက်အောင်)
            execSync(`ffmpeg -y -i temp_raw.mp4 -c:v libx264 -preset ultrafast -crf 28 -c:a aac "${output}"`);
            console.log("✅ ဒေါင်းလုဒ် အောင်မြင်သည်။");
        } else {
            throw new Error("File not found after download.");
        }
    } catch (e) {
        console.error("❌ YouTube Download Error:", e.message);
        throw e;
    }
}

// TikTok Upload Part (မပြောင်းလဲပါ)
async function uploadToTikTok(videoPath, caption) {
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
        await new Promise(r => setTimeout(r, 45000)); 
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
    let taskSnap = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
    if (taskSnap.empty) {
        taskSnap = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
        if (taskSnap.empty) return console.log("💤 Task မရှိသေးပါ။");
        const taskDoc = taskSnap.docs[0];
        const { videoUrl, movieName } = taskDoc.data();
        try {
            downloadVideo(videoUrl, "raw.mp4");
            console.log("✂️ ဗီဒီယို ဖြတ်နေပါသည်...");
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

    const taskDoc = taskSnap.docs[0];
    const { movieName } = taskDoc.data();
    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();
    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        if (!fs.existsSync(`part_${fileIndex}.mp4`)) return;
        execSync(`ffmpeg -y -i "part_${fileIndex}.mp4" -vf "drawtext=text='${label}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=80" "final.mp4"`);
        await uploadToTikTok("final.mp4", `${movieName} - ${label} #foryou #fyp #tiktok`);
        await partDoc.ref.update({ status: 'completed' });
        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').count().get();
        if (remain.data().count === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}
startBot();
