/* ========================================================================
   Zero Operators — Website v2 · behavior
   Minimal JS. Scroll reveals, theme toggle, oracle animation,
   memory stream, copy button. No dependencies.
   ======================================================================== */

(() => {
  'use strict';

  /* --------------------------------------------------------------
     MARK · inline SVG injection (Simplified C · the locked logo)
     -------------------------------------------------------------- */
  function zoMark(color = 'currentColor', accent = 'var(--coral)', size = 22, animate = false) {
    return `<svg width="${size}" height="${size}" viewBox="0 0 72 72" fill="none" aria-hidden="true">
      <circle cx="36" cy="36" r="30" stroke="${color}" stroke-width="2"/>
      <line x1="14" y1="58" x2="30" y2="42" stroke="${color}" stroke-width="2.4" stroke-linecap="round"/>
      <line x1="42" y1="30" x2="58" y2="14" stroke="${color}" stroke-width="2.4" stroke-linecap="round"/>
      <circle cx="36" cy="36" r="3.5" fill="${accent}"${animate ? ' class="pulse-dot"' : ''}/>
    </svg>`;
  }

  const navMark = document.getElementById('nav-mark');
  if (navMark) navMark.innerHTML = zoMark('var(--cream)', 'var(--coral)', 22);

  const footerMark = document.getElementById('footer-mark');
  if (footerMark) footerMark.innerHTML = zoMark('var(--cream)', 'var(--coral)', 40, true);

  /* --------------------------------------------------------------
     THEME · persist in localStorage, respect prefers-color-scheme
     -------------------------------------------------------------- */
  const root = document.documentElement;
  const stored = (() => {
    try { return localStorage.getItem('zo-theme'); } catch { return null; }
  })();
  const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
  const initial = stored || (prefersLight ? 'light' : 'dark');
  root.setAttribute('data-theme', initial);

  const toggleBtn = document.getElementById('theme-toggle');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const current = root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('zo-theme', next); } catch {}
    });
  }

  /* --------------------------------------------------------------
     NAV · add border + bg once we've scrolled past the hero line
     -------------------------------------------------------------- */
  const nav = document.getElementById('nav');
  const onScroll = () => {
    if (!nav) return;
    if (window.scrollY > 24) nav.classList.add('is-scrolled');
    else nav.classList.remove('is-scrolled');
  };
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  /* --------------------------------------------------------------
     REVEAL · IntersectionObserver for [data-reveal]
     Supports .reveal (generic) + .idea-diagram (custom animation)
     -------------------------------------------------------------- */
  const reveals = document.querySelectorAll('.reveal');
  // Apply delay as --delay var so CSS transition-delay works
  reveals.forEach((el) => {
    const d = el.getAttribute('data-delay');
    if (d) el.style.setProperty('--delay', d);
  });

  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-in');
        // trigger associated side-effects
        if (entry.target.classList.contains('split-card') && entry.target.dataset.card === 'oracle') {
          animateOracle(entry.target);
        }
        if (entry.target.classList.contains('split-card') && entry.target.dataset.card === 'memory') {
          animateMemory(entry.target);
        }
        if (entry.target.classList.contains('tmux-stage')) {
          animateTeam(entry.target);
        }
        if (entry.target.id === 'terminal') {
          entry.target.classList.add('is-live');
        }
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0.2, rootMargin: '0px 0px -80px 0px' });

  reveals.forEach((el) => io.observe(el));

  // Idea diagram animation is driven by .reveal's is-in class
  // (CSS targets .idea-diagram.is-in); nothing extra needed here.

  /* --------------------------------------------------------------
     AGENT TEAM · static tmux capture, live clock + subtle cursor
     Content reads like a real session; JS only drives the clock
     and a soft typewriter pulse on the cursor line.
     -------------------------------------------------------------- */
  function animateTeam(section) {
    const tmuxTime = section.querySelector('#tmux-time');
    const wbDate = section.querySelector('#wb-date');
    if (!tmuxTime) return;

    const pad = (n) => String(n).padStart(2, '0');
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    function stamp() {
      const d = new Date();
      const hh = pad(d.getHours());
      const mm = pad(d.getMinutes());
      const day = pad(d.getDate());
      const mon = months[d.getMonth()];
      const yr = String(d.getFullYear()).slice(2);
      return `${hh}:${mm} ${day}-${mon}-${yr}`;
    }
    const update = () => {
      const s = stamp();
      tmuxTime.textContent = s;
      if (wbDate) wbDate.textContent = s;
    };
    update();
    setInterval(update, 30000);
  }

  /* --------------------------------------------------------------
     ORACLE · metric counter + check flipping
     -------------------------------------------------------------- */
  function animateOracle(card) {
    const numEl = card.querySelector('#metric-num');
    const badge = card.querySelector('#oracle-badge');
    const badgeText = badge ? badge.querySelector('.badge-text') : null;
    const checks = card.querySelectorAll('.oracle-checks li');

    // Counter: 0 → 99.1
    const target = 99.1;
    const duration = 1400;
    const start = performance.now();
    function tick(now) {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic
      const val = (target * eased).toFixed(1);
      if (numEl) numEl.textContent = val + '%';
      if (p < 1) requestAnimationFrame(tick);
      else if (numEl) numEl.textContent = target.toFixed(1) + '%';
    }
    requestAnimationFrame(tick);

    // Staggered pass
    checks.forEach((li, i) => {
      const delay = 400 + i * 280;
      setTimeout(() => {
        const state = li.querySelector('.check-state');
        if (state) {
          state.setAttribute('data-state', 'pass');
          state.textContent = 'pass';
        }
      }, delay);
    });

    // Final badge flip
    setTimeout(() => {
      if (badgeText) badgeText.textContent = 'Verified';
    }, 400 + checks.length * 280 + 200);
  }

  /* --------------------------------------------------------------
     MEMORY · stream lines in one by one
     -------------------------------------------------------------- */
  function animateMemory(card) {
    const lines = card.querySelectorAll('.mem-line');
    lines.forEach((line, i) => {
      setTimeout(() => {
        line.classList.add('is-in');
      }, 220 + i * 320);
    });
  }

  /* --------------------------------------------------------------
     COPY BUTTON · copy the full command block
     -------------------------------------------------------------- */
  const copyBtn = document.getElementById('copy-btn');
  const termBody = document.getElementById('term-body');
  const copyLabel = document.getElementById('copy-label');

  if (copyBtn && termBody) {
    // Extract just the commands (lines beginning with ❯)
    function extractCommands() {
      const raw = termBody.textContent;
      return raw
        .split('\n')
        .filter(line => line.trim().startsWith('❯'))
        .map(line => line.replace(/^\s*❯\s*/, ''))
        .join('\n');
    }

    copyBtn.addEventListener('click', async () => {
      const text = extractCommands();
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.classList.add('copied');
        if (copyLabel) copyLabel.textContent = 'Copied';
        setTimeout(() => {
          copyBtn.classList.remove('copied');
          if (copyLabel) copyLabel.textContent = 'Copy';
        }, 1600);
      } catch {
        if (copyLabel) copyLabel.textContent = 'Failed';
        setTimeout(() => {
          if (copyLabel) copyLabel.textContent = 'Copy';
        }, 1600);
      }
    });
  }

  /* --------------------------------------------------------------
     SMOOTH SCROLL · for nav anchor links (respects reduced motion)
     -------------------------------------------------------------- */
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener('click', (e) => {
      const href = anchor.getAttribute('href');
      if (!href || href === '#') return;
      const target = document.querySelector(href);
      if (!target) return;
      e.preventDefault();
      const y = target.getBoundingClientRect().top + window.scrollY - 64;
      window.scrollTo({ top: y, behavior: reducedMotion ? 'auto' : 'smooth' });
    });
  });

  /* --------------------------------------------------------------
     MOBILE DRAWER · hamburger toggle, scrim/esc/link close
     -------------------------------------------------------------- */
  const burger = document.getElementById('nav-burger');
  const drawer = document.getElementById('mobile-drawer');

  function openDrawer() {
    if (!drawer || !burger) return;
    drawer.classList.add('is-open');
    drawer.setAttribute('aria-hidden', 'false');
    burger.setAttribute('aria-expanded', 'true');
    burger.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }
  function closeDrawer() {
    if (!drawer || !burger) return;
    drawer.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    burger.setAttribute('aria-expanded', 'false');
    burger.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  if (burger) {
    burger.addEventListener('click', () => {
      if (drawer && drawer.classList.contains('is-open')) closeDrawer();
      else openDrawer();
    });
  }
  if (drawer) {
    drawer.querySelectorAll('[data-md-close]').forEach((el) => {
      el.addEventListener('click', closeDrawer);
    });
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && drawer && drawer.classList.contains('is-open')) closeDrawer();
  });
  // Close drawer if user resizes back to desktop
  window.addEventListener('resize', () => {
    if (window.innerWidth > 900 && drawer && drawer.classList.contains('is-open')) closeDrawer();
  });

})();
