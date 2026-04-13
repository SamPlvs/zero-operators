// Intersection Observer for scroll-triggered animations
// Handles: [data-animate], [data-animate-stagger], [data-scroll-drive]

const animateObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      animateObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.15 });

document.querySelectorAll('[data-animate], [data-animate-stagger]').forEach(el => {
  animateObserver.observe(el);
});

// Scroll-driven progress for Pipeline section
const scrollDriveElements = document.querySelectorAll('[data-scroll-drive]');

if (scrollDriveElements.length > 0) {
  const updateScrollProgress = () => {
    scrollDriveElements.forEach(el => {
      const rect = el.getBoundingClientRect();
      const viewHeight = window.innerHeight;
      const elHeight = rect.height;

      // Progress: 0 when top enters viewport, 1 when bottom leaves
      const totalScroll = elHeight + viewHeight;
      const scrolled = viewHeight - rect.top;
      const progress = Math.max(0, Math.min(1, scrolled / totalScroll));

      el.style.setProperty('--scroll-progress', progress.toFixed(3));

      // Activate phase nodes based on progress
      const phases = el.querySelectorAll('.phase-node');
      const step = 1 / (phases.length || 1);
      phases.forEach((phase, i) => {
        if (progress >= step * i + step * 0.3) {
          phase.classList.add('active');
        } else {
          phase.classList.remove('active');
        }
      });
    });
    requestAnimationFrame(updateScrollProgress);
  };
  requestAnimationFrame(updateScrollProgress);
}
