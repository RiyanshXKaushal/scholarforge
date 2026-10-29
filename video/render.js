// Renders scene.html to video, one deterministic frame at a time.
//   node render.js out.mp4            full silent render
//   node render.js --stills 3,9,14    PNG previews at those seconds
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');

const FPS = 30, TOTAL = 1080;
const write = (stream, buf) => new Promise(res => stream.write(buf) ? res() : stream.once('drain', res));

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  await page.goto('file://' + path.join(__dirname, 'scene.html'));
  await page.evaluate(() => document.fonts.ready);

  const args = process.argv.slice(2);
  if (args[0] === '--stills') {
    for (const s of args[1].split(',').map(Number)) {
      await page.evaluate(t => render(t), s);
      await page.screenshot({ path: path.join(args[2] || '.', `still_${s}.png`) });
    }
    return browser.close();
  }

  const out = args[0] || 'silent.mp4';
  const ffmpeg = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p', out], { stdio: ['pipe', 'inherit', 'inherit'] });

  for (let f = 0; f < TOTAL; f++) {
    await page.evaluate(t => render(t), f / FPS);
    const frame = await page.screenshot({ type: 'jpeg', quality: 94 });
    await write(ffmpeg.stdin, frame);
    if (f % 120 === 0) console.log(`frame ${f}/${TOTAL}`);
  }
  ffmpeg.stdin.end();
  await new Promise(res => ffmpeg.on('close', res));
  await browser.close();
})();
