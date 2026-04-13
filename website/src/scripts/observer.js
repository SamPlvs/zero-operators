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
// Phases activate when they reach the center of the viewport and STAY active
const scrollDriveElements = document.querySelectorAll('[data-scroll-drive]');

if (scrollDriveElements.length > 0) {
  const updateScrollProgress = () => {
    const viewCenter = window.innerHeight / 2;

    scrollDriveElements.forEach(el => {
      const rect = el.getBoundingClientRect();
      const viewHeight = window.innerHeight;
      const elHeight = rect.height;

      const totalScroll = elHeight + viewHeight;
      const scrolled = viewHeight - rect.top;
      const progress = Math.max(0, Math.min(1, scrolled / totalScroll));

      el.style.setProperty('--scroll-progress', progress.toFixed(3));

      // Activate phase nodes when their center crosses the viewport center
      // Once active, they STAY active (never remove the class)
      const phases = el.querySelectorAll('.phase-node');
      phases.forEach((phase) => {
        const phaseRect = phase.getBoundingClientRect();
        const phaseCenter = phaseRect.top + phaseRect.height / 2;

        if (phaseCenter <= viewCenter + 100) {
          phase.classList.add('active');
        }
      });
    });
    requestAnimationFrame(updateScrollProgress);
  };
  requestAnimationFrame(updateScrollProgress);
}
