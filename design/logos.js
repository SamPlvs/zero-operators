// Logo exploration — rendered as inline SVG, shared across the system preview
// Brand is Zero Operators. Goal: no orbital / targeting motif. Warm, confident, developer-friendly.

window.ZO_LOGOS = {
  // ─── MONOGRAM family (primary brand mark candidates) ─────────────
  monogramStack: (color = '#EBE3D2', accent = 'var(--coral)', size = 120) => `
    <svg width="${size}" height="${size}" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- Z-O stacked monogram. Serif. Z crossbar is a horizon line, O has a notched opening. -->
      <!-- Z (top-left) -->
      <path d="M 18 18 L 58 18 L 22 54 L 58 54" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      <!-- horizon stroke (through the Z crossbar, extending) -->
      <path d="M 14 36 L 66 36" stroke="${accent}" stroke-width="1.5" stroke-linecap="round" opacity="0.75"/>
      <!-- O (bottom-right) with opening -->
      <path d="M 86 62 A 26 26 0 1 0 86 114 A 26 26 0 0 0 104 108" stroke="${color}" stroke-width="3" stroke-linecap="round" fill="none"/>
      <!-- Ember dot in the O's opening -->
      <circle cx="108" cy="88" r="3" fill="${accent}"/>
    </svg>
  `,

  monogramInline: (color = '#EBE3D2', accent = 'var(--coral)', size = 100) => `
    <svg width="${size * 1.8}" height="${size}" viewBox="0 0 180 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- ZO side by side, interlocking. -->
      <!-- Z -->
      <path d="M 20 22 L 70 22 L 26 78 L 70 78" stroke="${color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      <!-- interlocking horizon -->
      <line x1="60" y1="50" x2="108" y2="50" stroke="${accent}" stroke-width="1.8" stroke-linecap="round" opacity="0.85"/>
      <!-- O -->
      <circle cx="130" cy="50" r="28" stroke="${color}" stroke-width="3.5" fill="none"/>
      <!-- port notch -->
      <line x1="152" y1="42" x2="160" y2="42" stroke="${accent}" stroke-width="2.2" stroke-linecap="round"/>
    </svg>
  `,

  // ─── LIGHTHOUSE family (alt identity: quiet, works at 16px) ──────
  lighthouseDot: (color = '#EBE3D2', accent = 'var(--coral)', size = 100, animated = false) => `
    <svg width="${size}" height="${size}" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- vertical pillar (tapering) -->
      <path d="M 47 80 L 47 30 L 53 30 L 53 80 Z" fill="${color}"/>
      <!-- base -->
      <rect x="42" y="80" width="16" height="4" fill="${color}"/>
      <rect x="38" y="84" width="24" height="3" fill="${color}"/>
      <!-- glow lantern -->
      <circle cx="50" cy="22" r="7" fill="${accent}" ${animated ? 'class="pulse-dot"' : ''}/>
      <!-- light cone (soft) -->
      <path d="M 28 14 L 50 22 L 28 30 Z" fill="${accent}" opacity="0.18"/>
      <path d="M 72 14 L 50 22 L 72 30 Z" fill="${accent}" opacity="0.18"/>
    </svg>
  `,

  lighthouseMinimal: (color = '#EBE3D2', accent = 'var(--coral)', size = 100, animated = false) => `
    <svg width="${size * 0.6}" height="${size}" viewBox="0 0 60 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- single stroke + dot: the icon at its most reduced. -->
      <line x1="30" y1="84" x2="30" y2="26" stroke="${color}" stroke-width="4" stroke-linecap="round"/>
      <circle cx="30" cy="16" r="6" fill="${accent}" ${animated ? 'class="pulse-dot"' : ''}/>
      <line x1="22" y1="86" x2="38" y2="86" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
    </svg>
  `,

  // ─── WORKSHOP LAMP family (most character, evokes the illustration) ────
  workshopLamp: (color = '#EBE3D2', accent = 'var(--coral)', size = 100) => `
    <svg width="${size}" height="${size}" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- architect's lamp, tilted. Cone of warm light on the left. -->
      <!-- light cone -->
      <path d="M 32 38 L 8 72 L 38 72 Z" fill="${accent}" opacity="0.22"/>
      <!-- base -->
      <ellipse cx="68" cy="84" rx="14" ry="3" fill="${color}"/>
      <!-- upright -->
      <line x1="68" y1="84" x2="68" y2="52" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
      <!-- elbow -->
      <circle cx="68" cy="52" r="2.8" fill="${color}"/>
      <!-- arm -->
      <line x1="68" y1="52" x2="44" y2="38" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/>
      <!-- shade -->
      <path d="M 44 38 L 36 30 L 28 44 L 36 50 Z" fill="${color}"/>
      <!-- bulb -->
      <circle cx="32" cy="40" r="2.5" fill="${accent}"/>
    </svg>
  `,

  // ─── PLAN / NOTEBOOK family (concept-driven: "the plan is the only lever") ────
  planMark: (color = '#EBE3D2', accent = 'var(--coral)', size = 100) => `
    <svg width="${size}" height="${size}" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- page with folded corner -->
      <path d="M 24 18 L 68 18 L 82 32 L 82 84 L 24 84 Z" stroke="${color}" stroke-width="2.5" fill="none" stroke-linejoin="round"/>
      <!-- fold -->
      <path d="M 68 18 L 68 32 L 82 32" stroke="${color}" stroke-width="2.5" fill="none" stroke-linejoin="round"/>
      <!-- rule lines -->
      <line x1="34" y1="46" x2="70" y2="46" stroke="${color}" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
      <line x1="34" y1="56" x2="64" y2="56" stroke="${color}" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
      <!-- the "lever" — one accent line -->
      <line x1="34" y1="66" x2="50" y2="66" stroke="${accent}" stroke-width="2" stroke-linecap="round"/>
    </svg>
  `,

  // ─── ABSTRACT: NIGHT & DAY / BRIDGE (two-state identity) ────
  bridge: (color = '#EBE3D2', accent = 'var(--coral)', size = 100) => `
    <svg width="${size}" height="${size}" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- horizon line -->
      <line x1="12" y1="58" x2="88" y2="58" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
      <!-- two towers -->
      <line x1="28" y1="58" x2="28" y2="28" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
      <line x1="72" y1="58" x2="72" y2="28" stroke="${color}" stroke-width="3" stroke-linecap="round"/>
      <!-- cable curve (the plan arcs between them) -->
      <path d="M 28 28 Q 50 48 72 28" stroke="${accent}" stroke-width="2" fill="none" stroke-linecap="round"/>
      <!-- dots on the cable = agents -->
      <circle cx="40" cy="34" r="2" fill="${accent}"/>
      <circle cx="50" cy="38" r="2" fill="${accent}"/>
      <circle cx="60" cy="34" r="2" fill="${accent}"/>
      <!-- base line -->
      <line x1="22" y1="74" x2="78" y2="74" stroke="${color}" stroke-width="1.5" stroke-linecap="round" opacity="0.4"/>
    </svg>
  `,

  // ─── GEOMETRIC: THE NULL SET / ZERO-O (most typographic) ────
  nullMark: (color = '#EBE3D2', accent = 'var(--coral)', size = 100) => `
    <svg width="${size}" height="${size}" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- "Zero" expressed as a circle with a diagonal slash -->
      <!-- but this one has a soft break instead of a hard slash -->
      <circle cx="50" cy="50" r="32" stroke="${color}" stroke-width="3" fill="none"/>
      <!-- diagonal: two strokes with a gap where the "operators" removed themselves -->
      <line x1="28" y1="72" x2="44" y2="56" stroke="${accent}" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="56" y1="44" x2="72" y2="28" stroke="${accent}" stroke-width="2.5" stroke-linecap="round"/>
    </svg>
  `,

  // ─── SMALL — wordmark inline (for headers) ────────
  wordmarkInline: (color = '#EBE3D2', accent = 'var(--coral)', size = 22) => `
    <span style="font-family: var(--serif); font-weight: 400; font-size: ${size}px; letter-spacing: -0.01em; color: ${color};">
      Zero<span style="font-style: italic; color: ${accent};">Operators</span>
    </span>
  `,

  wordmarkTwoLine: (color = '#EBE3D2', accent = 'var(--coral)', size = 22) => `
    <span style="font-family: var(--serif); font-weight: 400; font-size: ${size}px; letter-spacing: -0.01em; color: ${color}; display: inline-flex; flex-direction: column; line-height: 0.95;">
      <span>Zero</span>
      <span style="font-style: italic; color: ${accent};">Operators</span>
    </span>
  `,
};
