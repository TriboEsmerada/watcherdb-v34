/**
 * WatcherDB Security Utilities
 * Sanitizes HTML before DOM insertion to prevent XSS
 *
 * SETUP: For full protection, load DOMPurify before this script:
 *   <script src="/static/vendor/dompurify/purify.min.js"></script>
 *   <script src="/static/js/security_utils.js"></script>
 *
 * Download DOMPurify 3.x from:
 *   https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js
 *   Place it at: static/vendor/dompurify/purify.min.js
 */
(function(global) {
    'use strict';

    // Use DOMPurify if loaded, otherwise basic fallback
    function safeHTML(element, html) {
        if (typeof DOMPurify !== 'undefined') {
            element.innerHTML = DOMPurify.sanitize(html, {
                ALLOWED_TAGS: ['div','span','i','p','h3','h4','h5','ul','li','ol',
                              'button','strong','em','pre','code','a','br',
                              'table','tr','td','th','thead','tbody',
                              'svg','path','circle','rect','line','polyline'],
                ALLOWED_ATTR: ['class','id','style','href','target','data-question',
                              'data-action','title','viewBox','d','fill','stroke',
                              'stroke-width','cx','cy','r','x','y','width','height',
                              'points','role','aria-label']
            });
        } else {
            // Fallback: escape HTML entities for safety
            var temp = document.createElement('div');
            temp.textContent = html;
            element.innerHTML = temp.innerHTML;
        }
    }

    global.safeHTML = safeHTML;
})(window);
