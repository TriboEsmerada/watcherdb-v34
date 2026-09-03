/**
 * WatcherDB Security Utilities (TypeScript version)
 * Sanitizes HTML before DOM insertion to prevent XSS
 */

import DOMPurify from 'dompurify';

const ALLOWED_CONFIG: DOMPurify.Config = {
  ALLOWED_TAGS: [
    'div', 'span', 'i', 'p', 'h3', 'h4', 'h5', 'ul', 'li', 'ol',
    'button', 'strong', 'em', 'pre', 'code', 'a', 'br',
    'table', 'tr', 'td', 'th', 'thead', 'tbody',
    'svg', 'path', 'circle', 'rect', 'line', 'polyline',
  ],
  ALLOWED_ATTR: [
    'class', 'id', 'style', 'href', 'target', 'data-question',
    'data-action', 'title', 'viewBox', 'd', 'fill', 'stroke',
    'stroke-width', 'cx', 'cy', 'r', 'x', 'y', 'width', 'height',
    'points', 'role', 'aria-label',
  ],
};

export function safeHTML(element: HTMLElement, html: string): void {
  element.innerHTML = DOMPurify.sanitize(html, ALLOWED_CONFIG);
}

// Expose globally for non-TS code
(window as any).safeHTML = safeHTML;
