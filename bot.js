const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

// Firebase Setup
const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
admin.initializeApp({ 
    credential: admin.credential.cert(serviceAccount),
    storageBucket: "yttott-28862.firebasestorage.app" // မိတ်ဆွေရဲ့ Bucket Name
});
const db = admin.firestore();
const bucket = admin.storage().bucket();

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
        
        console.log("⏳ Video Uploading to TikTok...");
        await new Promise(r => setTimeout(r, 45000)); 

        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(caption);

        await new Promise(r => setTimeout(r, 10000));
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
        if (taskSnap.empty) return console.log("💤 No tasks.");

        const taskDoc = taskSnap.docs[0];
        const { movieName, videoUrl } = taskDoc.data(); 

        console.log("📥 Downloading from Firebase Storage...");
        execSync(`curl -L "${videoUrl}" -o "input_video.mp4"`);

        console.log("✂️ Splitting video...");
        execSync(`ffmpeg -i "input_video.mp4" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);

        const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
        for (let i = 0; i < files.length; i++) {
            const label = (i === files.length - 1) ? "End Part" : `Part ${i+1}`;
            await taskDoc.ref.collection('parts').doc(`p${i}`).set({ fileIndex: i, label: label, status: 'pending' });
        }
        await taskDoc.ref.update({ status: 'processing' });
    }

    const taskDoc = taskSnap.docs[0];
    const { movieName, videoUrl } = taskDoc.data();
    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();

    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        const inputPath = `part_${fileIndex}.mp4`;

        // စာသားထည့်ခြင်း
        execSync(`ffmpeg -y -i "${inputPath}" -vf "drawtext=text='${label}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=80" "final.mp4"`);

        await uploadToTikTok("final.mp4", `${movieName} - ${label} #foryou #fyp #tiktok`);
        await partDoc.ref.update({ status: 'completed' });

        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').count().get();
        
        // 🔥 အကုန်တင်ပြီးသွားရင် အပိုင်းလိုက်ဖျက်မည်
        if (remain.data().count === 0) {
            console.log("🧹 Task ပြီးဆုံးပါပြီ။ Storage နှင့် Local ဖိုင်များကို ရှင်းလင်းနေပါသည်...");
            
            try {
                // ၁။ Firebase Storage မှ ဖျက်ခြင်း
                const fileUrl = new URL(videoUrl);
                const filePath = decodeURIComponent(fileUrl.pathname.split('/o/')[1].split('?')[0]);
                await bucket.file(filePath).delete();
                console.log("🗑️ Storage file deleted.");

                // ၂။ Local Files များကို ရှင်းခြင်း
                execSync('rm -rf part_*.mp4 input_video.mp4 final.mp4');
                
                await taskDoc.ref.update({ status: 'completed' });
            } catch (e) {
                console.error("Cleanup Error:", e.message);
            }
        }
    }
}

startBot();
