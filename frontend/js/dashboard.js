/**
 * dashboard.js — Compatibility shim for the new home-based dashboard.
 *
 * The old dashboard KPI elements no longer exist in the new UI.
 * This module is kept for compatibility and simply delegates to HomeModule.
 */

window.DashboardModule = (() => {
  async function refresh() {
    // Delegate to HomeModule for document list refresh
    if (window.HomeModule?.refresh) {
      await window.HomeModule.refresh();
    }

    // Update inconsistency badge if data is available
    if (App.currentDocId) {
      try {
        const data = await API.getDashboardData(App.currentDocId);
        const incs = data.inconsistency_summary || {};
        const total = incs.total ?? 0;

        const navBadge = document.getElementById('nav-badge-consistency');
        if (navBadge) {
          if (total > 0) {
            navBadge.textContent = total;
            navBadge.classList.remove('hidden');
          } else {
            navBadge.classList.add('hidden');
          }
        }
      } catch (err) {
        // Not critical — just skip badge update
      }
    }
  }

  return { refresh };
})();
