// DHHD Main JS

// Sidebar toggle (mobile)
const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('sidebarOverlay');
const toggleBtn = document.getElementById('sidebarToggle');

function openSidebar() {
  sidebar?.classList.add('open');
  overlay?.classList.add('open');
}
function closeSidebar() {
  sidebar?.classList.remove('open');
  overlay?.classList.remove('open');
}
toggleBtn?.addEventListener('click', openSidebar);
overlay?.addEventListener('click', closeSidebar);

// Auto-dismiss alerts
document.querySelectorAll('.alert[data-auto-dismiss]').forEach(el => {
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.5s'; setTimeout(() => el.remove(), 500); }, 4000);
});

// Confirm delete
document.querySelectorAll('[data-confirm]').forEach(el => {
  el.addEventListener('click', e => {
    if (!confirm(el.dataset.confirm || 'Are you sure?')) e.preventDefault();
  });
});

// Dynamic selects (geography cascade)
function cascadeSelect(triggerEl, targetEl, url, paramName) {
  if (!triggerEl || !targetEl) return;
  triggerEl.addEventListener('change', async function() {
    const val = this.value;
    targetEl.innerHTML = '<option value="">---------</option>';
    if (!val) return;
    try {
      const res = await fetch(`${url}?${paramName}=${val}`);
      const data = await res.json();
      data.forEach(item => {
        const opt = document.createElement('option');
        opt.value = item.id;
        opt.textContent = item.name;
        targetEl.appendChild(opt);
      });
    } catch(e) { console.error('Cascade select error:', e); }
  });
}

// PWA install prompt
let deferredPrompt;
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  deferredPrompt = e;
  const installBtn = document.getElementById('installBtn');
  if (installBtn) {
    installBtn.style.display = 'flex';
    installBtn.addEventListener('click', () => {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.then(() => { deferredPrompt = null; installBtn.style.display = 'none'; });
    });
  }
});

// Register service worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}