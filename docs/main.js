// Fade-in on scroll
document.addEventListener('DOMContentLoaded', () => {
  const targets = document.querySelectorAll('.feature-card, .screenshot-card, .step');
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );
  targets.forEach((el) => observer.observe(el));
});
