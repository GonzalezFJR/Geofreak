/* ============================================================
   GeoFreak — Shared JS Utilities
   Loaded globally via base.html before page-specific scripts.
   ============================================================ */

var GeoFreak = window.GeoFreak || {};

/** Escape a string for safe insertion into HTML. */
GeoFreak.escapeHtml = function (str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
};
