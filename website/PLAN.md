# Plan: Zero Operators Landing Page (zerooperators.com)

## Context

ZO needs a public-facing website at `zerooperators.com` (domain purchased via Namecheap). The site should be a clean, dark-mode single-page landing site inspired by [paperclip.ing](https://paperclip.ing/) — vertical scroll narrative with **rich animated visual demos per capability section**, progressive disclosure, terminal-style CTAs, and **clear positioning sections** (differentiation, before/after, why it's special, what it's not). The site will use ZO's existing brand system (amber #F0C040 on void #080808, Share Tech Mono + Rajdhani, orbital mark logo) and draw content from the README, PRD, and design assets already in the repo. Cloudflare Pages will host it. The architecture must support future agentic auto-updates (ZO agents updating content via JSON data files).

The final plan will also be saved to `website/PLAN.md` for ongoing reference.

---

## Decisions

- **Stack**: Astro 5 (static site generator, free/OSS, zero JS by default)
- **Location**: `website/` subdirectory in the ZO repo (agents can update in-repo)
- **Hosting**: Cloudflare Pages (build from subdirectory, custom domain)
- **Scope**: Single-page landing with rich animated feature sections + positioning narrative (v1)

---

## Project Structure

```
website/
  PLAN.md                    # This plan, kept for reference
  astro.config.mjs
  package.json
  tsconfig.json
  public/
    favicon.svg              # Copy of design/logo-dark.svg
    robots.txt
  src/
    layouts/
      Base.astro             # HTML shell, fonts, meta, global CSS, observer script
    pages/
      index.astro            # Single page composing all sections
    components/
      # --- Navigation ---
      Header.astro           # Fixed nav: logo + GitHub link/stars
      # --- Hero ---
      Hero.astro             # Full-viewport hero with orbital background
      # --- Narrative ---
      WhatIsIt.astro         # "What is this" intro + flow visual
      BeforeAfter.astro      # Life without ZO vs with ZO (seesaw)
      # --- Deep-dive features ---
      Pipeline.astro         # 6-phase animated pipeline
      OracleVerification.astro  # Tiered validation dashboard
      MemoryEvolution.astro  # Memory timeline + self-evolution flow
      ContractSpawning.astro # Expanding contract card animation
      # --- Positioning ---
      Differentiation.astro  # How ZO differs from other tools
      WhySpecial.astro       # What makes ZO unique
      WhatItsNot.astro       # Clear boundaries
      # --- Social proof & action ---
      AgentTeam.astro        # Agent roster grid
      QuickStart.astro       # Terminal-style command block
      Proof.astro            # Animated stats counters
      Footer.astro           # Logo, links, copyright
      # --- Shared ---
      OrbitalMark.astro      # Reusable inline SVG logo
    styles/
      global.css             # CSS custom properties, reset, typography, animations
    scripts/
      observer.js            # Shared intersection observer for scroll triggers
      counters.js            # Animated number counters for Proof section
    data/
      agents.json            # Agent roster (auto-updatable by ZO)
      stats.json             # Proof numbers (auto-updatable by ZO)
      pipeline.json          # Phase definitions for pipeline visual
      comparisons.json       # Before/after and differentiation content
```

**Key design choice**: Content lives in `src/data/*.json` files so ZO agents can auto-update numbers (test count, agent count, accuracy) without touching component code.

---

## Page Sections (top to bottom)

Each section follows the paperclip pattern: **headline + subheadline + rich visual or narrative**.

### 1. Header (fixed)
- Orbital mark (28px) + "ZERO OPERATORS" logotype (Rajdhani 600)
- Right: GitHub icon link + star count (fetched at build time, no client JS)

### 2. Hero (100vh)
- Orbital field SVG background (from `design/zero_operators_abstract_visuals.html`)
- "ZERO OPERATORS" — Rajdhani 700, 48-64px, letter-spacing 0.14em
- "AUTONOMOUS AI SYSTEMS" — Share Tech Mono 11px, amber-dim
- Tagline: "You input a plan. Agents execute. The oracle verifies."
- CTAs: "Get Started" (amber) + "View on GitHub" (outlined)
- Animated scroll indicator

### 3. What Is It — "Autonomous Research & Engineering"
- 3-4 sentence narrative from README
- Visual: animated plan.md → agent team → delivery repo flow diagram (SVG with data flowing as particles/pulses along the path)

### 4. Before/After — "What changes"
**The seesaw section.** Two-column layout showing life WITHOUT vs WITH ZO.

- **Visual**: Split panel, left side dim/grey (the old way), right side amber-lit (ZO way). A subtle dividing line or gradient between them.

**WITHOUT ZO (left, dim):**
| Problem | Reality |
|---------|---------|
| Context lost every session | "Where were we? Let me re-read everything..." |
| No verification | "It says it works. Does it?" |
| Same mistakes repeated | Bug fixed Friday. Same bug Monday. |
| Manual coordination | 47 tabs, 12 prompts, copy-paste results between tools |
| No audit trail | "Who decided to drop that feature? When? Why?" |
| Infrastructure leaks | ZO configs mixed into the delivery repo |
| Ad-hoc workflow | "What's next? I guess we try training?" |

**WITH ZO (right, amber):**
| Solution | Reality |
|----------|---------|
| Memory persists across sessions | STATE.md + DECISION_LOG + semantic search. Resume exactly where you left off. |
| Oracle verifies every claim | Hard metrics, tiered criteria, statistical significance. Nothing ships unverified. |
| Self-evolution prevents recurrence | 21 priors accumulated. Zero repeated failures. |
| One plan, autonomous execution | Write plan.md. Walk away. Come back to validated deliverables. |
| Complete audit trail | Every decision, every gate, every agent action — timestamped and searchable. |
| Clean repo separation | Delivery repo contains zero ZO artifacts. Always. |
| Structured 6-phase pipeline | Data → Features → Model → Training → Analysis → Packaging. Gated at every transition. |

- **Animation**: Left column items fade in first (in dim/muted style), then right column items "light up" in amber to show the contrast. The transition between dim and amber is the visual hook.

### 5. DEEP-DIVE: The Pipeline — "From data to delivery"
**The centrepiece visual.** Full-width animated 6-phase ML pipeline.

- **Visual**: Horizontal pipeline (desktop) / vertical (mobile) with 6 phase nodes connected by animated flow lines
- **Animation on scroll**: Each phase node lights up sequentially as user scrolls. Inactive phases dim (amber-ghost). Active phase pulses with glow. Data particles flow along connection lines.
- **Gate indicators**: Diamond-shaped gate markers. Human gates (phases 2, 5) pulse with person icon. Auto gates show check icon. On activation, gate "opens" with split animation.
- **Phase detail cards**: As each phase activates, a detail card slides in showing: phase name/number, key subtasks, assigned agents (tier badges), required artifacts.
- **Oracle loop**: Phase 4 (Training) has a visible iteration loop — arrow curving back with "iterate until oracle passes" label.
- **Scroll-locked**: Section is 200-300vh tall; scrolling drives animation frame by frame.

### 6. DEEP-DIVE: Oracle Verification — "Every claim is verified"
**Animated validation dashboard.**

- **Visual**: Mock dashboard panel with three tier rows:
  - **Must-pass** (red/green): accuracy >= 95%, tests passing, zero ZO artifacts
  - **Should-pass** (amber): coverage > 80%, clean lint, all phases complete
  - **Could-pass** (dim): statistical significance, reproducibility verified
- **Animation on scroll**:
  1. Dashboard frame appears (surface bg, amber border)
  2. Metric bars fill — accuracy 0% → 99% with counter
  3. Pass/fail badges flip from "PENDING" → "PASS" (green glow) one by one
  4. Three tiers reveal top to bottom with stagger
  5. Final: "VALIDATED" stamp pulses in
- **Text**: "No deliverable is deemed complete until the oracle confirms it."

### 7. DEEP-DIVE: Memory & Self-Evolution — "The same mistake never happens twice"
**Two-part animated sequence.**

**Part A — Memory Timeline** (left/top):
- Vertical timeline with decision entries sliding in:
  - `[DECISION] Architecture: Hybrid orchestration model`
  - `[GATE] Phase 1 complete — 76 tests passing`
  - `[CHECKPOINT] Human approved feature selection`
- Semantic search: search bar types "what did we try for feature selection?" → entries glow

**Part B — Self-Evolution** (right/bottom):
- Error → Post-mortem → Rule Update → Prevention flow:
  1. Red error flash: `ERROR: Doc-codebase drift — 10 files stale`
  2. Arrow → Root cause: `missing_rule — no enforcement`
  3. Arrow → PRIORS.md typewriter: `PR-005: Aspirational rules without enforcement are dead letter`
  4. Arrow → Green shield: "Three-layer defense implemented"
  5. Final: "21 priors accumulated. Zero repeated failures."

### 8. DEEP-DIVE: Contract-First Spawning — "Precision, not prompts"
**Expanding contract card animation.**

- Starts with a small card: `"Build a model"`
- On scroll, card expands step by step revealing:
  1. **Inputs**: `processed data at data/processed/, feature list from Phase 2`
  2. **Outputs**: `trained model at models/best.pt, training_metrics.jsonl, oracle evaluation`
  3. **Success criteria**: `accuracy >= 95%, inference < 100ms, reproducible with seed`
  4. **Precedent**: `DECISION_LOG: "Linear baseline scored 78%, try CNN next"`
  5. **Budget**: `max 5 iterations, 30 min wall clock`
  6. **Tools/Off-limits**: `PyTorch, CUDA` | `delivery repo configs, ZO infrastructure`
- **Side text**: "Every agent gets a precise contract. No ambiguity. No mid-execution clarifications."
- **Comparison**: "Before" vague prompt vs full contract side by side

### 9. Differentiation — "Not another coding assistant"
**How ZO differs from existing tools.** Grid or comparison layout.

- **Headline**: "What gap does ZO fill?"
- **Subheadline**: "Most AI tools help you write code. ZO replaces the need to coordinate it."

**Comparison grid** (reads from `comparisons.json`):

| Dimension | Coding assistants (Cursor, Copilot, Oh My Claude) | Agent frameworks (CrewAI, AutoGen, LangGraph) | **Zero Operators** |
|-----------|-----|-----|-----|
| **Unit of work** | Line/function | Task/step | **Entire project** |
| **Human role** | Pair programmer | Prompt engineer | **Research director** |
| **Verification** | "Looks right to me" | Optional checks | **Oracle-mandated, tiered, statistical** |
| **Memory** | Current session only | Basic state | **Persistent: STATE, DECISION_LOG, PRIORS, semantic search** |
| **Learning** | None | None | **Self-evolution: failures update rules** |
| **Delivery** | Code in your editor | Output files | **Clean repo, zero infrastructure artifacts** |
| **Workflow** | Ad-hoc | User-defined DAG | **6-phase gated pipeline with human checkpoints** |

- **Visual treatment**: The grid renders as cards or a styled table. The "Zero Operators" column is amber-highlighted. Other columns are dim. On scroll, the ZO column lights up row by row.
- **Key message**: "Coding assistants help you write lines. Agent frameworks help you chain tasks. ZO gives you a *team* that owns the project end-to-end — from plan to verified delivery."

### 10. Why ZO Is Special — "Why this exists"
**The soul of the project.** Text-forward section with a strong visual accent.

- **Headline**: "Why Zero Operators"
- **Layout**: Large pull-quote style, one statement per screen-third, each with a brief elaboration:

1. **"The plan is the only lever."**
   You don't prompt agents individually. You write one plan.md with objectives, metrics, and constraints. Agents decompose it, execute it, and verify it. If you want to change direction, edit the plan — agents detect the delta and replan.

2. **"The oracle is the source of truth."**
   Not "does the code compile?" Not "did the agent say it's done?" The oracle runs hard metrics against the actual output. 99% accuracy is either met or it isn't. No ambiguity. No hallucinated success.

3. **"The system learns from its own mistakes."**
   When something fails, ZO doesn't just fix it — it updates the rule that allowed the failure. PRIORS.md grows with every project. The same mistake literally cannot happen twice because the rule now prevents it.

4. **"Zero operators means zero humans in the loop during execution."**
   Humans approve the plan. Humans approve gate checkpoints. Everything between is autonomous. The name is the promise: zero human operators needed for the work itself.

- **Visual**: Each statement could be accompanied by the orbital mark or a geometric accent (radial lines, concentric rings) that ties back to the brand.

### 11. What ZO Is Not — "Clear boundaries"
**Crisp, honest positioning.** Short section with clean typography.

- **Headline**: "What Zero Operators is not"
- **Layout**: Two-column "Not X / It's Y" pattern, similar to paperclip's differentiation section:

| It is NOT... | It IS... |
|---|---|
| A coding assistant | A coordinated agent team that owns entire projects |
| A chatbot you prompt | An autonomous system you brief with a plan |
| A wrapper around LLMs | An orchestration engine with memory, verification, and self-evolution |
| A no-code tool | A specification-driven system — plan.md is precise, not simplified |
| A one-shot tool | A multi-session system with persistent memory and session recovery |
| Magic | Engineering discipline applied to AI coordination |

- **Visual**: Each row animates in with stagger. The "NOT" side is struck through (dim, line-through text). The "IS" side glows amber.
- **Closing line**: "ZO is a digital research and engineering team that happens to express itself in code, models, reports, and data artifacts."

### 12. Agent Team — "The Team"
- "20 agents. 3 tiers. Coordinated."
- Grid of agent cards: name, model tier badge (Opus/Sonnet/Haiku), role icon, 1-line description
- Staggered card animation. Reads from `agents.json`
- Responsive: 3-col → 2-col → 1-col

### 13. Quick Start — "Get Started"
- Terminal-themed block:
  ```
  git clone https://github.com/SamPlvs/zero-operators.git
  cd zero-operators && ./setup.sh
  zo init my-project
  zo draft --project my-project
  zo build plans/my-project.md
  ```
- Typewriter animation + blinking cursor

### 14. Proof — "Validated"
- 4 animated stat counters: **99%** (accuracy), **$11** (cost), **476** (tests), **20** (agents)
- Rajdhani 700 at ~72px, count-up animation on scroll
- Reads from `stats.json`

### 15. Footer
- Orbital mark centered
- "ZERO OPERATORS v1.0.1" + MIT License
- Links: GitHub, Docs (future)

---

## Animation Architecture

**Two JS modules** (kept minimal):

### `scripts/observer.js` (~40 lines)
- `[data-animate]`: simple fade-up on entry
- `[data-animate-stagger]`: children fade in with delay
- `[data-scroll-drive]`: progress-based animation (Pipeline section) — sets `--scroll-progress` CSS variable (0→1)
- Animate once then unobserve (except scroll-driven)

### `scripts/counters.js` (~20 lines)
- `[data-count-to="99"]`: counts from 0 to target over 1.5s with ease-out
- Supports suffix (%, $, +)

### Key CSS animations (in `global.css`)
- Fade-up, stagger, scroll-driven progress
- Pipeline phase activation (dim → lit with glow)
- Flow particles along connection lines (CSS offset-path)
- Contract card expansion (max-height transition)
- Typewriter cursor blink
- Before/after: dim → amber column lighting
- Strikethrough animation for "What it's NOT" items

**No animation libraries.** Pure CSS transitions + two small JS modules.

---

## Styling

- **CSS custom properties** matching the brand system exactly:
  - `--amber: #F0C040`, `--amber-dim: #8a6020`, `--void: #080808`, `--surface: #0d0d0d`
- **Fonts**: Google Fonts — Share Tech Mono + Rajdhani (300, 400, 600, 700) with `display=swap`
- **Scoped styles**: Each `.astro` component uses `<style>` (Astro scopes by default)
- **Responsive**: Mobile-first, breakpoints at 640px and 1024px. `clamp()` for fluid hero title
- **Dark mode only** — no light toggle

---

## Brand Assets to Reuse

| Asset | Source Path | Usage |
|-------|-----------|-------|
| Orbital mark SVG | `design/logo-dark.svg` | Inline in `OrbitalMark.astro`, copy to `public/favicon.svg` |
| Banner lockup | `design/banner-dark.svg` | Reference for Hero text hierarchy/spacing |
| Brand system CSS | `design/zero_operators_brand_system.html` | All CSS custom properties, component patterns |
| Abstract visuals | `design/zero_operators_abstract_visuals.html` | Hero background orbital field SVG |
| README content | `README.md` | Narrative text, agent table, quick start, stats |

---

## Implementation Order

### Step 1: Scaffold
- Create `website/` with `package.json` (astro dep), `astro.config.mjs`, `tsconfig.json`
- Copy `PLAN.md` into `website/`
- Copy favicon, create `robots.txt`
- Update root `.gitignore`
- `npm install` to verify

### Step 2: Foundation
- `global.css` — all brand tokens, reset, typography, animation classes
- `Base.astro` — HTML head (meta, OG tags, fonts), body shell
- `OrbitalMark.astro` — reusable SVG component
- `scripts/observer.js` + `scripts/counters.js`
- Skeleton `index.astro` — verify `npm run dev` shows dark page with fonts

### Step 3: Content Data
- `pipeline.json` — 6 phases with names, descriptions, agents, artifacts, gate types
- `agents.json` — 20 agents with name, model, role, team
- `stats.json` — 4 proof numbers
- `comparisons.json` — before/after items, differentiation grid, "what it's not" pairs

### Step 4: Hero + Narrative Sections
1. `Header.astro` — fixed nav with logo + GitHub stars
2. `Hero.astro` — full-viewport with orbital background, title, tagline, CTAs
3. `WhatIsIt.astro` — narrative + animated flow diagram
4. `BeforeAfter.astro` — without/with ZO split panel

### Step 5: Deep-Dive Feature Sections
5. `Pipeline.astro` — scroll-driven 6-phase pipeline animation
6. `OracleVerification.astro` — animated validation dashboard
7. `MemoryEvolution.astro` — memory timeline + self-evolution flow
8. `ContractSpawning.astro` — expanding contract card

### Step 6: Positioning Sections
9. `Differentiation.astro` — comparison grid vs other tools
10. `WhySpecial.astro` — four core statements
11. `WhatItsNot.astro` — "Not X / It's Y" with strikethrough animation

### Step 7: Action + Proof Sections
12. `AgentTeam.astro` — agent card grid
13. `QuickStart.astro` — terminal with typewriter
14. `Proof.astro` — animated stat counters
15. `Footer.astro`

### Step 8: Polish
- Test responsive at 375px / 768px / 1280px
- Verify all animations trigger correctly
- Accessibility check (heading hierarchy, contrast, keyboard nav)
- OG image placeholder
- Lighthouse audit

### Step 9: Deploy
- `npm run build` and verify `dist/`
- Set up Cloudflare Pages: build command `cd website && npm install && npm run build`, output `website/dist`
- Add custom domain `zerooperators.com` + `www.zerooperators.com`
- Namecheap: point nameservers to Cloudflare
- Verify live

---

## Verification

1. `cd website && npm run dev` — site loads locally, brand styling correct
2. `npm run build` — no errors, static HTML in `dist/`
3. Scroll through all 15 sections — animations trigger at correct scroll points
4. Before/After: dim column fades in, then amber column lights up
5. Pipeline: 6 phases light up sequentially on scroll
6. Oracle: metrics animate, badges flip to PASS
7. Memory: log entries slide in, search highlights
8. Contract: card expands step by step
9. Differentiation: ZO column highlights row by row
10. What It's Not: strikethrough animates on "NOT" items
11. Proof: counters animate from 0 to target values
12. Mobile (375px): all sections readable, pipeline vertical
13. Lighthouse: 90+ performance, 90+ accessibility
14. Live: `zerooperators.com` resolves and renders

---

## Files Created (30 new)

```
website/PLAN.md
website/astro.config.mjs
website/package.json
website/tsconfig.json
website/public/favicon.svg
website/public/robots.txt
website/src/layouts/Base.astro
website/src/pages/index.astro
website/src/components/Header.astro
website/src/components/Hero.astro
website/src/components/WhatIsIt.astro
website/src/components/BeforeAfter.astro
website/src/components/Pipeline.astro
website/src/components/OracleVerification.astro
website/src/components/MemoryEvolution.astro
website/src/components/ContractSpawning.astro
website/src/components/Differentiation.astro
website/src/components/WhySpecial.astro
website/src/components/WhatItsNot.astro
website/src/components/AgentTeam.astro
website/src/components/QuickStart.astro
website/src/components/Proof.astro
website/src/components/Footer.astro
website/src/components/OrbitalMark.astro
website/src/styles/global.css
website/src/scripts/observer.js
website/src/scripts/counters.js
website/src/data/agents.json
website/src/data/stats.json
website/src/data/pipeline.json
website/src/data/comparisons.json
```

## Files Modified (1)
```
.gitignore (append website ignores)
```
