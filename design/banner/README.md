# README banner — source files

Source files for the banner shown at the top of the project [README](../../README.md). The banner is composited from an SVG overlay + a raster photo. The SVG alone won't render the photo (the right-half image is drawn at composite-time, not embedded), so to regenerate the PNG you must run the render script.

## Files

| File | What it is |
|---|---|
| `readme-banner.svg` | Master overlay — typography, mark, frame ticks, fade gradient. **Edit this** to change copy, colors, mark, layout. The right-half photo is *not* embedded here. |
| `workshop.png` | Source photo for the right half (1536×1024, anime workshop scene). Identical to `website/public/assets/hero-workshop.png` — kept as a sibling here so the render script is self-contained. |
| `readme-banner.png` | Final composite, 1280×640. **This is what the README references.** |
| `readme-banner-2x.png` | Same composite at 2560×1280 for retina. |
| `render.mjs` | Render script — composites `workshop.png` + `readme-banner.svg` → final PNGs. Re-run after editing the SVG. |

## Render parameters (current values, baked into render.mjs)

| Param | Value | Why |
|---|---|---|
| Banner size | 1280 × 640 | Standard GitHub README banner. |
| Photo crop | sx=480, sy=112, sw=800, sh=800 | Crops out the lamp on the right and the cat in the corner; keeps the person + monitors + city. |
| Photo dest | x=560, y=-100, w=800, h=800 | Right half of the banner, with vertical bleed so the cityscape sits at the top. |
| Right clip | rect(560, 0, 720, 640) | Confines the photo to the right 56% of the banner. |
| Fade gradient | x: 420 → 820 (stops at 0/.35/.6/.85/1) | Soft transition from solid `#12110F` panel into the photo. |
| Mark | Simplified C (from `deploy/website/public/app.js`), 44px | Matches the live website's locked logo exactly. |

## How to regenerate

The full render logic lives in [`render.mjs`](./render.mjs) — that's the single source of truth, fully commented with edit points. It expects `workshop.png` and `readme-banner.svg` as siblings (so its working directory should be this `design/banner/` folder, or the four siblings dropped into a sandbox root).

It's written for the project's `run_script` sandbox (browser-side Canvas with helpers `readImage` / `readFile` / `createCanvas` / `saveFile`). To run from Node instead, swap those helpers for `fs` + `sharp` or `node-canvas` — the compositing logic itself is unchanged.

## To edit later

- **Change copy / colors / layout** → edit `readme-banner.svg` directly. The whole left-half composition is there as plain SVG text, so you can tweak headline, taglines, badges, mark color, etc.
- **Change the photo** → drop a new file at `workshop.png` (and update `website/public/assets/hero-workshop.png` to match if you want the website hero to follow). If you want a different crop, edit the `PHOTO_CROP` values in `render.mjs`.
- **Change the mark** → edit the `<g transform="translate(88,88) scale(0.6111)">` block in the SVG. Source-of-truth definition lives in [`website/public/app.js`](../../website/public/app.js) (`zoMark()`).
- **Re-render** → run `render.mjs` (writes `readme-banner.png` and `readme-banner-2x.png` next to it).
