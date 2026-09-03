/**
 * WatcherDB I18N Engine v2.0
 * ========================================
 * Complete internationalization system with:
 * - Interpolation: t('msg.welcome', { name: 'João' }) → "Bem-vindo, João"
 * - Pluralization: t('msg.results', { count: 5 }) → "5 resultados"
 * - Fallback chain: ES → EN → PT → key
 * - Lazy loading: PT inline, EN/ES loaded on demand
 * - MutationObserver: auto-translate dynamic DOM elements
 * - data-i18n attributes: declarative translation
 * - Persistence: localStorage
 *
 * Supports: PT-PT (default, pt.json), PT-BR (pt-BR.json = overlay esparso com fallback por chave para pt), EN, ES
 *
 * Usage:
 *   t('kpi.instances_ok')                        → simple translation
 *   t('msg.welcome', { name: 'João' })           → interpolation
 *   t('msg.results', { count: 5 })               → pluralization
 *   t('msg.showing', { count: 3, total: 10 })    → interpolation + plural
 *   setLanguage('en')                             → switch language
 *   getLanguage()                                 → current language code
 *   tCategory('Disponibilidade')                  → translate category name
 *   onLanguageChange(callback)                    → register change listener
 */

(function(global) {
    'use strict';

    // ========================================
    // CONFIGURATION
    // ========================================
    const DEFAULT_LANG = 'pt';
    const SUPPORTED_LANGS = ['pt', 'pt-BR', 'en', 'es'];
    const FALLBACK_CHAIN = {
        pt: ['pt'],
        'pt-BR': ['pt-BR', 'pt'],   // overlay esparso (decisao owner 2026-09-03)
        en: ['en', 'pt'],
        es: ['es', 'en', 'pt']
    };
    const I18N_BASE_PATH = '/static/i18n/';

    // ========================================
    // STATE
    // ========================================
    let _currentLang = DEFAULT_LANG;
    let _dictionaries = {};    // { lang: { key: value } }
    let _loading = {};         // { lang: Promise }
    let _changeListeners = []; // [ callback(lang) ]
    let _observer = null;      // MutationObserver
    let _initialized = false;

    // ========================================
    // CORE: TRANSLATION FUNCTION
    // ========================================

    /**
     * Translate a key with optional interpolation and pluralization.
     *
     * @param {string} key - Translation key (e.g., 'kpi.instances_ok')
     * @param {Object} [params] - Variables for interpolation/pluralization
     * @returns {string} Translated string
     *
     * Pluralization syntax in JSON:
     *   "msg.results": "{count} resultado|{count} resultados"
     *   Pipe separates: singular|plural (for PT/EN/ES)
     *
     * Interpolation syntax:
     *   "msg.welcome": "Bem-vindo, {name}"
     *   Variables in {curly braces} are replaced with params values
     */
    function t(key, params) {
        if (!key) return '';

        const chain = FALLBACK_CHAIN[_currentLang] || FALLBACK_CHAIN[DEFAULT_LANG];
        let raw = undefined;

        // Walk fallback chain
        for (const lang of chain) {
            const dict = _dictionaries[lang];
            if (dict && dict[key] !== undefined) {
                raw = dict[key];
                break;
            }
        }

        // Last resort: return the key itself
        if (raw === undefined) return key;

        // Handle pluralization (pipe-separated forms)
        if (raw.indexOf('|') !== -1 && params && params.count !== undefined) {
            raw = _pluralize(raw, params.count);
        }

        // Handle interpolation {variable}
        if (params) {
            raw = _interpolate(raw, params);
        }

        return raw;
    }

    /**
     * Pluralize a pipe-separated string.
     * Format: "singular|plural" or "zero|singular|plural"
     */
    function _pluralize(raw, count) {
        const forms = raw.split('|');
        const n = Number(count);

        if (forms.length === 3) {
            // zero|singular|plural
            if (n === 0) return forms[0].trim();
            if (n === 1) return forms[1].trim();
            return forms[2].trim();
        }

        if (forms.length === 2) {
            // singular|plural
            return (n === 1) ? forms[0].trim() : forms[1].trim();
        }

        return forms[0].trim();
    }

    /**
     * Replace {variable} placeholders with params values.
     */
    function _interpolate(str, params) {
        return str.replace(/\{(\w+)\}/g, function(match, varName) {
            return params[varName] !== undefined ? params[varName] : match;
        });
    }

    // ========================================
    // CATEGORY TRANSLATION (legacy compat)
    // ========================================
    const _categoryKeyMap = {
        'Disponibilidade': 'cat.disponibilidade',
        'Performance': 'cat.performance',
        'Espaço': 'cat.espaco',
        'Espaco': 'cat.espaco',
        'Disco': 'cat.disco',
        'Backup': 'cat.backup',
        'Jobs': 'cat.jobs',
        'Alta Disponibilidade': 'cat.alta_disponibilidade'
    };

    function tCategory(categoryName) {
        const key = _categoryKeyMap[categoryName];
        return key ? t(key) : categoryName;
    }

    // ========================================
    // LANGUAGE MANAGEMENT
    // ========================================

    /**
     * Get current language code.
     * @returns {string} 'pt', 'en', or 'es'
     */
    function getLanguage() {
        return _currentLang;
    }

    /**
     * Set the current language.
     * Loads dictionary if not cached, then applies to UI.
     *
     * @param {string} lang - Language code ('pt', 'pt-BR', 'en', 'es')
     * @returns {Promise<void>}
     */
    async function setLanguage(lang) {
        if (!SUPPORTED_LANGS.includes(lang)) {
            console.warn('[I18N] Unsupported language:', lang);
            return;
        }

        // Load dictionary if not yet loaded
        if (!_dictionaries[lang]) {
            await _loadDictionary(lang);
        }

        _currentLang = lang;
        localStorage.setItem('watcherdb_lang', lang);

        // Update HTML lang attribute
        const langMap = { pt: 'pt-PT', 'pt-BR': 'pt-BR', en: 'en', es: 'es' };  // norma PT-PT pos-AO90 (decisao owner 2026-08-16)
        document.documentElement.lang = langMap[lang] || lang;

        // Update selector visual
        _updateSelector();

        // Apply translations to visible UI
        applyLanguageToUI();

        // Notify listeners
        _changeListeners.forEach(function(cb) {
            try { cb(lang); } catch(e) { console.error('[I18N] Listener error:', e); }
        });

        console.log('[I18N] Language changed to:', lang);
    }

    /**
     * Register a callback for language changes.
     * @param {Function} callback - Called with new lang code
     * @returns {Function} Unsubscribe function
     */
    function onLanguageChange(callback) {
        _changeListeners.push(callback);
        return function() {
            _changeListeners = _changeListeners.filter(function(cb) { return cb !== callback; });
        };
    }

    // ========================================
    // DICTIONARY LOADING
    // ========================================

    /**
     * Load a language dictionary from JSON file.
     * Caches the result in _dictionaries.
     */
    async function _loadDictionary(lang) {
        if (_loading[lang]) {
            return _loading[lang];
        }

        _loading[lang] = (async function() {
            try {
                const url = I18N_BASE_PATH + lang + '.json?v=' + Date.now();
                const resp = await fetch(url);
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();

                // Flatten nested keys if needed: { kpi: { ok: 'OK' } } → { 'kpi.ok': 'OK' }
                _dictionaries[lang] = _flattenDict(data);

                console.log('[I18N] Loaded ' + lang + '.json (' + Object.keys(_dictionaries[lang]).length + ' keys)');
            } catch(e) {
                console.error('[I18N] Failed to load ' + lang + '.json:', e);
                _dictionaries[lang] = {};
            } finally {
                delete _loading[lang];
            }
        })();

        return _loading[lang];
    }

    /**
     * Flatten a nested dictionary into dot-notation keys.
     * Supports both flat and nested JSON formats.
     *
     * Input:  { kpi: { ok: 'OK', off: 'Off' }, ui: { loading: '...' } }
     * Output: { 'kpi.ok': 'OK', 'kpi.off': 'Off', 'ui.loading': '...' }
     *
     * Also accepts already-flat: { 'kpi.ok': 'OK' } → { 'kpi.ok': 'OK' }
     */
    function _flattenDict(obj, prefix, result) {
        result = result || {};
        prefix = prefix || '';

        for (var key in obj) {
            if (!obj.hasOwnProperty(key)) continue;
            var fullKey = prefix ? prefix + '.' + key : key;

            if (typeof obj[key] === 'object' && obj[key] !== null && !Array.isArray(obj[key])) {
                _flattenDict(obj[key], fullKey, result);
            } else {
                result[fullKey] = String(obj[key]);
            }
        }

        return result;
    }

    /**
     * Register an inline dictionary (for PT which loads eagerly).
     * Called from the HTML or from the JSON inline embed.
     */
    function registerDictionary(lang, dict) {
        _dictionaries[lang] = _flattenDict(dict);
        console.log('[I18N] Registered ' + lang + ' dictionary (' + Object.keys(_dictionaries[lang]).length + ' keys)');
    }

    // ========================================
    // DOM: APPLY TRANSLATIONS
    // ========================================

    /**
     * Apply translations to all visible UI elements.
     * Handles: data-i18n, data-i18n-placeholder, data-i18n-title,
     *          data-i18n-aria, and specific known elements.
     */
    function applyLanguageToUI() {
        // 1. Translate all elements with data-i18n attribute
        var elements = document.querySelectorAll('[data-i18n]');
        for (var i = 0; i < elements.length; i++) {
            _translateElement(elements[i]);
        }

        // 2. Translate placeholders
        var placeholders = document.querySelectorAll('[data-i18n-placeholder]');
        for (var i = 0; i < placeholders.length; i++) {
            var key = placeholders[i].getAttribute('data-i18n-placeholder');
            var translated = t(key);
            if (translated !== key) {
                placeholders[i].placeholder = translated;
            }
        }

        // 3. Translate title/tooltip attributes
        var titles = document.querySelectorAll('[data-i18n-title]');
        for (var i = 0; i < titles.length; i++) {
            var key = titles[i].getAttribute('data-i18n-title');
            var translated = t(key);
            if (translated !== key) {
                titles[i].title = translated;
            }
        }

        // 4. Translate aria-labels
        var ariaLabels = document.querySelectorAll('[data-i18n-aria]');
        for (var i = 0; i < ariaLabels.length; i++) {
            var key = ariaLabels[i].getAttribute('data-i18n-aria');
            var translated = t(key);
            if (translated !== key) {
                ariaLabels[i].setAttribute('aria-label', translated);
            }
        }

        // 5. Update known fixed elements (legacy compatibility)
        _updateKnownElements();

        // 6. Update KPI metadata translations if available
        if (typeof updateKPIMetadataTranslations === 'function') {
            try { updateKPIMetadataTranslations(); } catch(e) {}
        }

        // 7. Re-render open tabs and dashboard
        _refreshOpenContent();
    }

    /**
     * Translate a single element with data-i18n.
     * Supports data-i18n-params for interpolation.
     */
    function _translateElement(el) {
        var key = el.getAttribute('data-i18n');
        if (!key) return;

        // Parse params from data-i18n-params (JSON string)
        var params = null;
        var paramsAttr = el.getAttribute('data-i18n-params');
        if (paramsAttr) {
            try { params = JSON.parse(paramsAttr); } catch(e) {}
        }

        var translated = t(key, params);
        if (translated !== key) {
            // Preserve child icons (e.g., <i class="fas fa-...">)
            var icon = el.querySelector('i.fas, i.far, i.fab, i.fa');
            if (icon && el.childNodes.length <= 2) {
                // Element has icon + text: preserve icon, replace text
                el.textContent = '';
                el.appendChild(icon);
                el.appendChild(document.createTextNode(' ' + translated));
            } else {
                el.textContent = translated;
            }
        }
    }

    /**
     * Update specific known UI elements (header, search, buttons).
     * Legacy compatibility with v1 applyLanguageToUI.
     */
    function _updateKnownElements() {
        // Search placeholder
        var searchInput = document.getElementById('searchInput');
        if (searchInput) searchInput.placeholder = t('header.search_placeholder');

        // Dashboard button
        var dashboardBtn = document.querySelector('[onclick="goToDashboardKPIs()"]');
        if (dashboardBtn) {
            var icon = dashboardBtn.querySelector('i');
            dashboardBtn.innerHTML = '';
            if (icon) dashboardBtn.appendChild(icon);
            dashboardBtn.appendChild(document.createTextNode(' ' + t('header.dashboard_kpis')));
            dashboardBtn.title = t('header.dashboard_title');
        }

        // Ping button
        var pingBtn = document.getElementById('pingButton');
        if (pingBtn) pingBtn.title = t('header.ping_title');

        // Settings button
        var settingsBtn = document.querySelector('[onclick="openSettingsModal()"]');
        if (settingsBtn) settingsBtn.title = t('header.settings');

        // Settings modal header
        var settingsHeader = document.querySelector('#settingsModal .modal-header h3');
        if (settingsHeader) safeHTML(settingsHeader, '<i class="fas fa-cog"></i> ' + t('modal.settings'));

        // Service logs modal title
        var logsTitle = document.getElementById('serviceLogsModalTitle');
        if (logsTitle) safeHTML(logsTitle, '<i class="fas fa-scroll"></i> ' + t('modal.service_logs'));

        // KPI Documentation modal title
        var kpiHelpTitle = document.getElementById('kpiHelpModalTitle');
        if (kpiHelpTitle) safeHTML(kpiHelpTitle, '<i class="fas fa-book" style="margin-right: 8px;"></i>' + t('doc.title'));

        // KPI Help search placeholder
        var kpiHelpSearch = document.getElementById('kpiHelpSearch');
        if (kpiHelpSearch) kpiHelpSearch.placeholder = t('doc.search_placeholder');

        // KPI Help button
        var kpiHelpBtn = document.querySelector('[onclick="showKPIHelpModal()"]');
        if (kpiHelpBtn) kpiHelpBtn.title = t('doc.help_title');

        // Sidebar label
        var sidebarLabel = document.getElementById('sidebarServersLabel');
        if (sidebarLabel) sidebarLabel.textContent = t('sidebar.servers');
    }

    /**
     * Refresh open tabs and dashboard to apply new translations.
     */
    function _refreshOpenContent() {
        try {
            if (typeof openTabs !== 'undefined' && openTabs && openTabs.values) {
                for (var tab of openTabs.values()) {
                    if (typeof refreshTab === 'function') {
                        refreshTab(tab.id);
                    }
                }
            }
            if (typeof renderDashboardCards === 'function') {
                var contentArea = document.getElementById('mainContentArea');
                if (contentArea && contentArea.querySelector('#kpi-dashboard-container')) {
                    renderDashboardCards();
                }
            }
        } catch (e) {
            // openTabs or refreshTab may not be initialized yet
        }
    }

    // ========================================
    // LANGUAGE SELECTOR COMPONENT
    // ========================================

    /**
     * Update the visual state of the language selector dropdown.
     */
    function _updateSelector() {
        var selector = document.getElementById('langSelector');
        if (selector) selector.value = _currentLang;

        // Update flag display if custom selector
        var flagDisplay = document.getElementById('langFlagDisplay');
        if (flagDisplay) {
            var flags = { pt: '🇵🇹', 'pt-BR': '🇧🇷', en: '🇺🇸', es: '🇪🇸' };
            var labels = { pt: 'PT', 'pt-BR': 'PT-BR', en: 'EN', es: 'ES' };
            safeHTML(flagDisplay, flags[_currentLang] + ' ' + labels[_currentLang]);
        }
    }

    /**
     * Create and inject the language selector into the header.
     * Call this from the portal HTML after DOM is ready.
     *
     * @param {string|HTMLElement} targetSelector - CSS selector or element to append to
     */
    function createLanguageSelector(targetSelector) {
        var target = typeof targetSelector === 'string'
            ? document.querySelector(targetSelector)
            : targetSelector;

        if (!target) {
            console.warn('[I18N] Language selector target not found:', targetSelector);
            return;
        }

        var container = document.createElement('div');
        container.className = 'i18n-lang-selector';
        container.setAttribute('role', 'navigation');
        container.setAttribute('aria-label', 'Language selector');

        safeHTML(container, [
            '<button class="i18n-lang-btn" id="langToggleBtn" aria-haspopup="listbox" aria-expanded="false">',
            '  <span id="langFlagDisplay">🇵🇹 PT</span>',
            '  <i class="fas fa-chevron-down i18n-lang-chevron"></i>',
            '</button>',
            '<div class="i18n-lang-dropdown" id="langDropdown" role="listbox" aria-label="Select language">',
            '  <div class="i18n-lang-option" data-lang="pt" role="option" lang="pt-PT">',
            '    <span class="i18n-lang-flag">🇵🇹</span>',
            '    <span class="i18n-lang-name">Português (Portugal)</span>',
            '    <i class="fas fa-check i18n-lang-check"></i>',
            '  </div>',
            '  <div class="i18n-lang-option" data-lang="pt-BR" role="option" lang="pt-BR">',
            '    <span class="i18n-lang-flag">🇧🇷</span>',
            '    <span class="i18n-lang-name">Português (Brasil)</span>',
            '    <i class="fas fa-check i18n-lang-check"></i>',
            '  </div>',
            '  <div class="i18n-lang-option" data-lang="en" role="option" lang="en">',
            '    <span class="i18n-lang-flag">🇺🇸</span>',
            '    <span class="i18n-lang-name">English</span>',
            '    <i class="fas fa-check i18n-lang-check"></i>',
            '  </div>',
            '  <div class="i18n-lang-option" data-lang="es" role="option" lang="es">',
            '    <span class="i18n-lang-flag">🇪🇸</span>',
            '    <span class="i18n-lang-name">Español</span>',
            '    <i class="fas fa-check i18n-lang-check"></i>',
            '  </div>',
            '</div>'
        ].join('\n'));

        target.appendChild(container);

        // Event: toggle dropdown
        var btn = container.querySelector('#langToggleBtn');
        var dropdown = container.querySelector('#langDropdown');

        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var isOpen = dropdown.classList.toggle('open');
            btn.setAttribute('aria-expanded', isOpen);
        });

        // Event: select language
        var options = container.querySelectorAll('.i18n-lang-option');
        for (var i = 0; i < options.length; i++) {
            options[i].addEventListener('click', function(e) {
                var lang = this.getAttribute('data-lang');
                setLanguage(lang);
                dropdown.classList.remove('open');
                btn.setAttribute('aria-expanded', 'false');
                // Update active state
                container.querySelectorAll('.i18n-lang-option').forEach(function(opt) {
                    opt.classList.toggle('active', opt.getAttribute('data-lang') === lang);
                });
            });
        }

        // Close on outside click
        document.addEventListener('click', function() {
            dropdown.classList.remove('open');
            btn.setAttribute('aria-expanded', 'false');
        });

        // Mark current language as active
        var currentOpt = container.querySelector('[data-lang="' + _currentLang + '"]');
        if (currentOpt) currentOpt.classList.add('active');

        _updateSelector();
    }

    // ========================================
    // MUTATION OBSERVER: AUTO-TRANSLATE NEW DOM
    // ========================================

    /**
     * Start observing DOM for dynamically added elements with data-i18n.
     */
    function _startObserver() {
        if (_observer || typeof MutationObserver === 'undefined') return;

        _observer = new MutationObserver(function(mutations) {
            var needsTranslation = false;

            for (var i = 0; i < mutations.length; i++) {
                var added = mutations[i].addedNodes;
                for (var j = 0; j < added.length; j++) {
                    var node = added[j];
                    if (node.nodeType !== 1) continue; // only elements

                    if (node.hasAttribute && node.hasAttribute('data-i18n')) {
                        _translateElement(node);
                        needsTranslation = true;
                    }

                    // Check children
                    if (node.querySelectorAll) {
                        var children = node.querySelectorAll('[data-i18n], [data-i18n-placeholder], [data-i18n-title]');
                        for (var k = 0; k < children.length; k++) {
                            if (children[k].hasAttribute('data-i18n')) {
                                _translateElement(children[k]);
                            }
                            if (children[k].hasAttribute('data-i18n-placeholder')) {
                                var pKey = children[k].getAttribute('data-i18n-placeholder');
                                var pVal = t(pKey);
                                if (pVal !== pKey) children[k].placeholder = pVal;
                            }
                            if (children[k].hasAttribute('data-i18n-title')) {
                                var tKey = children[k].getAttribute('data-i18n-title');
                                var tVal = t(tKey);
                                if (tVal !== tKey) children[k].title = tVal;
                            }
                        }
                    }
                }
            }
        });

        _observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        console.log('[I18N] MutationObserver started');
    }

    // ========================================
    // INITIALIZATION
    // ========================================

    /**
     * Initialize the i18n system.
     * - Loads PT dictionary (inline or from JSON)
     * - Restores user language preference
     * - Starts MutationObserver
     */
    async function init(inlinePtDict) {
        if (_initialized) return;
        _initialized = true;

        // Register PT dictionary (inline for instant availability)
        if (inlinePtDict) {
            registerDictionary('pt', inlinePtDict);
        } else {
            await _loadDictionary('pt');
        }

        // Restore user preference
        var savedLang = localStorage.getItem('watcherdb_lang');
        if (savedLang && SUPPORTED_LANGS.includes(savedLang)) {
            _currentLang = savedLang;
        }

        // Load current language dict if not PT
        if (_currentLang !== 'pt' && !_dictionaries[_currentLang]) {
            await _loadDictionary(_currentLang);
        }

        // Set HTML lang attribute
        var langMap = { pt: 'pt-PT', 'pt-BR': 'pt-BR', en: 'en', es: 'es' };  // norma PT-PT pos-AO90 (decisao owner 2026-08-16)
        document.documentElement.lang = langMap[_currentLang] || _currentLang;

        // Start MutationObserver for dynamic content
        if (document.body) {
            _startObserver();
        } else {
            document.addEventListener('DOMContentLoaded', _startObserver);
        }

        // Apply translations to UI once everything is ready
        if (document.body) {
            applyLanguageToUI();
        } else {
            document.addEventListener('DOMContentLoaded', function() {
                applyLanguageToUI();
            });
        }

        console.log('[I18N] Initialized. Language:', _currentLang,
            '| PT keys:', Object.keys(_dictionaries.pt || {}).length);
    }

    // ========================================
    // UTILITY: BULK TRANSLATE HTML STRING
    // ========================================

    /**
     * Translate an HTML string by replacing data-i18n markers.
     * Useful for template literals that build HTML dynamically.
     *
     * @param {string} html - HTML string with data-i18n attributes
     * @returns {string} HTML with translated text
     */
    function translateHTML(html) {
        // Replace patterns like: data-i18n="key">fallback text</
        return html.replace(/data-i18n="([^"]+)">[^<]*/g, function(match, key) {
            var translated = t(key);
            return 'data-i18n="' + key + '">' + translated;
        });
    }

    /**
     * Helper: check if a key exists in any loaded dictionary.
     */
    function hasKey(key) {
        for (var lang in _dictionaries) {
            if (_dictionaries[lang][key] !== undefined) return true;
        }
        return false;
    }

    /**
     * Helper: get all keys for a language (for debugging/validation).
     */
    function getKeys(lang) {
        return Object.keys(_dictionaries[lang] || {});
    }

    /**
     * Helper: get dictionary stats.
     */
    function getStats() {
        var stats = {};
        for (var lang in _dictionaries) {
            stats[lang] = Object.keys(_dictionaries[lang]).length;
        }
        stats.currentLang = _currentLang;
        return stats;
    }

    // ========================================
    // PUBLIC API
    // ========================================
    global.WatcherI18N = {
        t: t,
        tCategory: tCategory,
        setLanguage: setLanguage,
        getLanguage: getLanguage,
        onLanguageChange: onLanguageChange,
        applyLanguageToUI: applyLanguageToUI,
        createLanguageSelector: createLanguageSelector,
        registerDictionary: registerDictionary,
        translateHTML: translateHTML,
        hasKey: hasKey,
        getKeys: getKeys,
        getStats: getStats,
        init: init,
        SUPPORTED_LANGS: SUPPORTED_LANGS
    };

    // Backward-compatible global functions
    global.t = t;
    global.tCategory = tCategory;
    global.setLanguage = setLanguage;
    global.getLanguage = getLanguage;
    global.applyLanguageToUI = applyLanguageToUI;

})(typeof window !== 'undefined' ? window : this);
