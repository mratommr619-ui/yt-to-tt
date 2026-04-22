const admin = require('firebase-admin');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

// ၁။ Firebase Setup (GitHub Secrets ထဲကနေ ဖတ်မယ်)
const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
});
const db = admin.firestore();

// ၂။ TikTok သို့ Video တင်ခြင်း Function
async function uploadToTikTok(videoPath, movieName, partLabel) {
    console.log(`🤖 TikTok သို့တင်နေသည်: ${movieName} (${partLabel})`);
    
    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();
    const cookies = JSON.parse(process.env.TIKTOK_COOKIES);
    await page.setCookie(...cookies);

    try {
        await page.goto('https://www.tiktok.com/creator-center/upload?from=upload', { waitUntil: 'networkidle2' });
        
        // ဖိုင်ရွေးချယ်ခြင်း
        const fileInput = await page.$('input[type="file"]');
        await fileInput.uploadFile(videoPath);
        console.log("📤 Upload တင်နေသည်... (ခဏစောင့်ပါ)");
        await new Promise(r => setTimeout(r, 25000)); // ဗီဒီယိုတင်ဖို့ စက္ကန့် ၂၅ စောင့်မယ်

        // Caption ရိုက်ခြင်း (Video Name + Part + Hashtags)
        const fullCaption = `${movieName} (${partLabel}) #foryou #fyp #tiktok #movie #review`;
        console.log(`✍️ Caption: ${fullCaption}`);
        
        await page.waitForSelector('.public-DraftEditor-content');
        await page.click('.public-DraftEditor-content');
        
        // စာဟောင်းရှိရင်ဖျက်ပြီး အသစ်ရိုက်မယ်
        await page.keyboard.down('Control');
        await page.keyboard.press('A');
        await page.keyboard.up('Control');
        await page.keyboard.press('Backspace');
        await page.keyboard.sendCharacter(fullCaption);

        await new Promise(r => setTimeout(r, 5000));

        // Publish နှိပ်မယ်
        await page.click('button[class*="button-post"]');
        console.log(`✅ ${partLabel} အောင်မြင်စွာ တင်ပြီးပါပြီ!`);
        
    } catch (err) {
        console.error("❌ Error uploading to TikTok:", err.message);
    } finally {
        await browser.close();
    }
}

// ၃။ ဗီဒီယိုပေါ်တွင် Part Number စာသားရေးခြင်း (FFMPEG)
async function addTextToVideo(inputPath, outputPath, text) {
    console.log(`🎬 ဗီဒီယိုပေါ်တွင်စာသားရေးနေသည်: ${text}`);
    // ဗီဒီယိုအပေါ်ဘက် အလယ်တည့်တည့်မှာ စာလုံးအဖြူ၊ နောက်ခံအမည်းနဲ့ ရေးပါမယ်
    const ffmpegCmd = `ffmpeg -i "${inputPath}" -vf "drawtext=text='${text}':fontcolor=white:fontsize=70:box=1:boxcolor=black@0.6:boxborderw=15:x=(w-text_w)/2:y=60" -codec:a copy "${outputPath}"`;
    execSync(ffmpegCmd);
}

// ၄။ အဓိက Bot Function
async function startBot() {
    console.log("🚀 Bot စတင်နေပါပြီ...");
    const snapshot = await db.collection('tasks').where('status', '==', 'pending').limit(1).get();

    for (const doc of snapshot.docs) {
        const { videoUrl, taskId, movieName } = doc.data();
        const movieTitle = movieName || "New Movie"; // နာမည်မပါရင် New Movie လို့သုံးမယ်
        
        const rawVideo = `raw_${taskId}.mp4`;
        const outputFolder = `./parts_${taskId}`;
        if (!fs.existsSync(outputFolder)) fs.mkdirSync(outputFolder);

        try {
            // YouTube မှ ဒေါင်းခြင်း
            console.log("📥 YouTube မှ ဒေါင်းလုဒ်ဆွဲနေသည်...");
            execSync(`npx yt-dlp-exec "${videoUrl}" -o "${rawVideo}" -f "mp4"`);

            // ၅ မိနစ် (၃၀၀ စက္ကန့်) စီ ဖြတ်ခြင်း
            console.log("✂️ ဗီဒီယို ပိုင်းဖြတ်နေသည်...");
            execSync(`ffmpeg -i "${rawVideo}" -f segment -segment_time 300 -reset_timestamps 1 "${outputFolder}/part_%d.mp4"`);

            const parts = fs.readdirSync(outputFolder).filter(f => f.endsWith('.mp4'));
            const totalParts = parts.length;

            for (let i = 0; i < totalParts; i++) {
                const isLast = i === totalParts - 1;
                const partLabel = isLast ? "END Part" : `Part ${i + 1}`;
                const originalPart = `${outputFolder}/part_${i}.mp4`;
                const finalPart = `${outputFolder}/final_part_${i}.mp4`;

                // ၁။ ဗီဒီယိုပေါ် စာသားအရင်ထည့်မယ်
                await addTextToVideo(originalPart, finalPart, partLabel);

                // ၂။ TikTok တင်မယ်
                await uploadToTikTok(finalPart, movieTitle, partLabel);

                // ၃။ တစ်ပိုင်းတင်ပြီးရင် ၄၅ မိနစ် (၂၇၀၀ စက္ကန့်) စောင့်မယ်
                if (!isLast) {
                    console.log("⏳ ၄၅ မိနစ် နားနေပါသည် (Spam မဖြစ်အောင်)...");
                    await new Promise(r => setTimeout(r, 45 * 60 * 1000));
                }
            }

            // Task ပြီးကြောင်း Update လုပ်မယ်
            await db.collection('tasks').doc(doc.id).update({ status: 'completed' });
            console.log(`🎉 Task ${taskId} အားလုံး ပြီးဆုံးပါပြီ!`);

        } catch (err) {
            console.error("❌ Critical Error:", err.message);
        }
    }
}

startBot();
