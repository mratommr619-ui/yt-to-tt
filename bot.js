const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

// Firebase Setup
const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
admin.initializeApp({ credential: admin.credential.cert(serviceAccount) });
const db = admin.firestore();

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
        
        console.log("⌛ Video တက်အောင် ခဏစောင့်နေပါသည်...");
        await new Promise(r => setTimeout(r, 40000)); 

        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        await page.keyboard.sendCharacter(caption);

        await new Promise(r => setTimeout(r, 10000));
        await page.click('button[class*="button-post"]');
        console.log(`✅ တင်ပြီးပါပြီ: ${caption}`);
    } catch (err) {
        console.error("❌ TikTok Error:", err.message);
    } finally {
        await browser.close();
    }
}

async function startBot() {
    // လက်ရှိ လုပ်ဆောင်နေဆဲ Task ကို ရှာမည်
    let taskSnap = await db.collection('tasks').where('status', '==', 'processing').limit(1).get();
    
    if (taskSnap.empty) {
        // အသစ်တက်လာတဲ့ Task ကို ရှာမည်
        taskSnap = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();
        if (taskSnap.empty) return console.log("💤 တင်စရာ ဗီဒီယို မရှိသေးပါ။");

        const taskDoc = taskSnap.docs[0];
        const { movieName, localFileName } = taskDoc.data(); 

        // ဗီဒီယိုကို ၅ မိနစ်စီ ဖြတ်မည်
        console.log("✂️ ဗီဒီယို ဖြတ်နေပါသည်...");
        execSync(`ffmpeg -i "${localFileName}" -f segment -segment_time 300 -reset_timestamps 1 "part_%d.mp4"`);

        const files = fs.readdirSync('.').filter(f => f.startsWith('part_') && f.endsWith('.mp4'));
        for (let i = 0; i < files.length; i++) {
            const isLast = (i === files.length - 1);
            const label = isLast ? "End Part" : `Part ${i+1}`;
            await taskDoc.ref.collection('parts').doc(`p${i}`).set({ 
                fileIndex: i, 
                label: label, 
                status: 'pending' 
            });
        }
        await taskDoc.ref.update({ status: 'processing' });
    }

    const taskDoc = taskSnap.docs[0];
    const { movieName } = taskDoc.data();
    
    // တင်ရန် ကျန်နေသော အပိုင်းကို ရှာမည်
    const partSnap = await taskDoc.ref.collection('parts').where('status', '==', 'pending').orderBy('fileIndex').limit(1).get();

    if (!partSnap.empty) {
        const partDoc = partSnap.docs[0];
        const { fileIndex, label } = partDoc.data();
        const inputPath = `part_${fileIndex}.mp4`;

        // ဗီဒီယို Thumbnail ပေါ်မှာ Part နံပါတ် စာသားထည့်မည်
        console.log(`✍️ စာသားထည့်နေပါသည်: ${label}`);
        execSync(`ffmpeg -y -i "${inputPath}" -vf "drawtext=text='${label}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=80" "final_upload.mp4"`);

        const caption = `${movieName} - ${label} #foryou #fyp #tiktok #movie`;
        await uploadToTikTok("final_upload.mp4", caption);
        
        await partDoc.ref.update({ status: 'completed' });

        // အကုန်ပြီးမပြီး စစ်မည်
        const remain = await taskDoc.ref.collection('parts').where('status', '==', 'pending').count().get();
        if (remain.data().count === 0) await taskDoc.ref.update({ status: 'completed' });
    }
}

startBot();
