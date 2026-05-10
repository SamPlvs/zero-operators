/**
 * README banner — Node-runnable render script
 * ─────────────────────────────────────────────────────────────────────
 * Sibling of `render.mjs` (which is for the in-browser Canvas sandbox).
 * This one runs from Node + sharp, so any contributor who edits the
 * SVG copy can regenerate `readme-banner.png` and `readme-banner-2x.png`
 * locally without needing the sandbox.
 *
 * USAGE
 *   From the repo root:
 *     node design/banner/render-node.mjs
 *
 * REQUIREMENTS
 *   sharp 0.34+ (the website's node_modules already provides it; this
 *   script imports from there to avoid an extra install). librsvg under
 *   sharp resolves `xlink:href="workshop.png"` natively, but we inline
 *   the photo as a data URL for portability across rendering backends.
 *
 * EDIT POINTS
 *   - SVG (`readme-banner.svg`) — typography, mark, frame ticks, lede,
 *     badges. The compositing layout (dark panel + photo + fade) is
 *     baked into the SVG itself.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const sharpPath = resolve(here, '..', '..', 'website', 'node_modules', 'sharp');
const require = createRequire(import.meta.url);
const sharp = require(sharpPath);

const photoBuf = readFileSync(resolve(here, 'workshop.png'));
const photoData = 'data:image/png;base64,' + photoBuf.toString('base64');

let svg = readFileSync(resolve(here, 'readme-banner.svg'), 'utf8');
svg = svg.replace(/(xlink:)?href="workshop\.png"/g, '$1href="' + photoData + '"');

const W = 1280;
const H = 640;

async function render(scale, out) {
  const path = resolve(here, out);
  await sharp(Buffer.from(svg), { density: 72 * scale })
    .resize(W * scale, H * scale)
    .png()
    .toFile(path);
  console.log(`wrote ${out} (${W * scale}×${H * scale})`);
}

await render(1, 'readme-banner.png');
await render(2, 'readme-banner-2x.png');
