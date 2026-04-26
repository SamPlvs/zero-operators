/**
 * README banner — render script
 * ─────────────────────────────────────────────────────────────────────
 * Composites workshop.png + readme-banner.svg (both siblings of this
 * script) into:
 *   - readme-banner.png       (1280 x 640)
 *   - readme-banner-2x.png    (2560 x 1280, retina)
 *
 * The SVG holds the dark-panel typography + frame + mark. The right-half
 * photo is NOT embedded in the SVG — this script clips and draws it onto
 * the canvas, then layers the SVG on top.
 *
 * USAGE
 *   This is written for the project's `run_script` sandbox (browser-side
 *   Canvas with the helpers `readImage`, `readFile`, `createCanvas`,
 *   `saveFile`). Paths below are relative to whatever directory the
 *   sandbox treats as its cwd — point that at this `design/banner/`
 *   folder (or copy the four siblings into the sandbox root) before
 *   running. To run from Node instead, swap those helpers for `fs`,
 *   `sharp` or `node-canvas` equivalents — the compositing logic is
 *   otherwise self-contained.
 *
 * EDIT POINTS
 *   - PHOTO_CROP: which part of workshop.png ends up in the banner.
 *   - PHOTO_DEST: where it lands on the canvas (x/y/w/h).
 *   - FADE_*    : gradient transition from dark panel into photo.
 *   - The SVG itself: typography, mark, frame ticks, badges.
 */

const PHOTO_CROP = { sx: 480, sy: 112, sw: 800, sh: 800 };
const PHOTO_DEST = { dx: 560, dy: -100, dw: 800, dh: 800 };
const RIGHT_CLIP = { x: 560, y: 0, w: 720, h: 640 };
const FADE = {
  x1: 420, x2: 820,
  stops: [
    [0,    'rgba(18,17,15,1)'],
    [0.35, 'rgba(18,17,15,1)'],
    [0.6,  'rgba(18,17,15,0.7)'],
    [0.85, 'rgba(18,17,15,0.25)'],
    [1,    'rgba(18,17,15,0)'],
  ],
  rect: { x: 420, y: 0, w: 400, h: 640 },
};
const PANEL_BG = '#12110F';
const BANNER_W = 1280;
const BANNER_H = 640;

const photo = await readImage('workshop.png');
let svgText = await readFile('readme-banner.svg');

// The SVG contains placeholder rects/images that the canvas draws itself.
// Strip them so we don't double-paint or cover the photo.
svgText = svgText.replace(`<rect width="${BANNER_W}" height="${BANNER_H}" fill="${PANEL_BG}"></rect>`, '');
svgText = svgText.replace(/<image\b[^>]*?\/?>(?:<\/image>)?/g, '');
svgText = svgText.replace(/<rect x="500" y="0" width="480" height="640" fill="url\(#fade\)"><\/rect>/, '');

async function render(scale, outPath) {
  const W = BANNER_W * scale;
  const H = BANNER_H * scale;
  const cv = createCanvas(W, H);
  const ctx = cv.getContext('2d');

  // 1) dark panel base
  ctx.fillStyle = PANEL_BG;
  ctx.fillRect(0, 0, W, H);

  // 2) photo, clipped to the right half
  ctx.save();
  ctx.beginPath();
  ctx.rect(RIGHT_CLIP.x * scale, RIGHT_CLIP.y * scale, RIGHT_CLIP.w * scale, RIGHT_CLIP.h * scale);
  ctx.clip();
  ctx.drawImage(
    photo,
    PHOTO_CROP.sx, PHOTO_CROP.sy, PHOTO_CROP.sw, PHOTO_CROP.sh,
    PHOTO_DEST.dx * scale, PHOTO_DEST.dy * scale, PHOTO_DEST.dw * scale, PHOTO_DEST.dh * scale,
  );
  ctx.restore();

  // 3) fade gradient (panel → transparent over the photo)
  const grad = ctx.createLinearGradient(FADE.x1 * scale, 0, FADE.x2 * scale, 0);
  for (const [stop, color] of FADE.stops) grad.addColorStop(stop, color);
  ctx.fillStyle = grad;
  ctx.fillRect(FADE.rect.x * scale, FADE.rect.y * scale, FADE.rect.w * scale, FADE.rect.h * scale);

  // 4) SVG overlay (typography, mark, frame ticks, badges)
  const svgBlob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
  const svgUrl = URL.createObjectURL(svgBlob);
  const svgImg = new Image();
  await new Promise((res, rej) => {
    svgImg.onload = res;
    svgImg.onerror = rej;
    svgImg.src = svgUrl;
  });
  ctx.drawImage(svgImg, 0, 0, W, H);
  URL.revokeObjectURL(svgUrl);

  await saveFile(outPath, cv);
  log(`wrote ${outPath} (${W}×${H})`);
}

await render(1, 'readme-banner.png');
await render(2, 'readme-banner-2x.png');
