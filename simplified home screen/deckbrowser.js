/* Copyright: Ankitects Pty Ltd and contributors
 * License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html */

var simplifyCurrentTheme = null;
var simplifyThemeObserver = null;
var simplifyThemeConfig = window.smwThemeConfig || {};

function mergeThemeVars(defaults, overrides) {
    var result = Object.assign({}, defaults);
    if (overrides) {
        Object.keys(overrides).forEach(function (key) {
            if (overrides[key] !== undefined && overrides[key] !== null) {
                result[key] = overrides[key];
            }
        });
    }
    return result;
}

var simplifyLightVars = mergeThemeVars({
    "--smw-body-bg": "#f0f0f0",
    "--smw-card-bg": "#ffffff",
    "--smw-border-color": "#e5e5ea",
    "--smw-card-selected": "#f4f4f7",
    "--smw-text-color": "#1d1d1f",
    "--smw-muted-text": "#8e8e93",
    "--smw-accent-color": "#0a84ff",
    "--smw-due-color": "#34c759",
    "--smw-new-color": "#007aff",
    "--smw-tooltip-bg": "#000000",
    "--smw-tooltip-text": "#ffffff"
}, simplifyThemeConfig.light);

var simplifyDarkVars = mergeThemeVars({
    "--smw-body-bg": "#1e1e1e",
    "--smw-card-bg": "#2c2c2e",
    "--smw-border-color": "#3a3a3c",
    "--smw-card-selected": "#3a3a3c",
    "--smw-text-color": "#f5f5f7",
    "--smw-muted-text": "#c7c7cc",
    "--smw-accent-color": "#0a84ff",
    "--smw-due-color": "#30d158",
    "--smw-new-color": "#0a84ff",
    "--smw-tooltip-bg": "#000000",
    "--smw-tooltip-text": "#f5f5f7"
}, simplifyThemeConfig.dark);

function applySimplifyTheme(force) {
    var body = document.body;
    var root = document.documentElement || body;
    if (!body || !root) {
        return false;
    }
    var dark = body.classList.contains("nightMode");
    var theme = dark ? "dark" : "light";
    if (!force && simplifyCurrentTheme === theme) {
        return true;
    }
    simplifyCurrentTheme = theme;
    var vars = dark ? simplifyDarkVars : simplifyLightVars;
    Object.keys(vars).forEach(function (prop) {
        root.style.setProperty(prop, vars[prop]);
    });
    return true;
}

function initSimplifyThemeObserver() {
    if (!document.body || simplifyThemeObserver) {
        return;
    }
    simplifyThemeObserver = new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i++) {
            if (mutations[i].attributeName === "class") {
                applySimplifyTheme();
                break;
            }
        }
    });
    simplifyThemeObserver.observe(document.body, { attributes: true, attributeFilter: ["class"] });
}

if (!applySimplifyTheme(true)) {
    document.addEventListener("DOMContentLoaded", function handleSimplifyThemeInit() {
        document.removeEventListener("DOMContentLoaded", handleSimplifyThemeInit);
        applySimplifyTheme(true);
        initSimplifyThemeObserver();
    });
} else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSimplifyThemeObserver);
} else {
    initSimplifyThemeObserver();
}

function initDeckInteractions() {
    $("tr.deck").draggable({
        scroll: false,
        helper: function () {
            return $(this).clone(false);
        },
        delay: 200,
        opacity: 0.7
    });

    $("th.count").draggable({
        scroll: false,
        helper: function () {
            return $(this).clone(false);
        },
        delay: 200,
        opacity: 0.7
    });

    $("tr.deck").droppable({
        drop: handleDropEvent,
        hoverClass: 'drag-hover'
    });
    $("th.count").droppable({
        drop: columnDropEvent,
        hoverClass: 'drag-hover'
    });
    $("tr.top-level-drag-row").droppable({
        drop: handleDropEvent,
        hoverClass: 'drag-hover'
    });

    // Simple cursor feedback without keyboard selection state
    $(document).on('mouseenter', '.ios-row-card', function () {
        this.classList.add('ios-row-hover');
    });
    $(document).on('mouseleave', '.ios-row-card', function () {
        this.classList.remove('ios-row-hover');
    });
    $(document).on('click', '.ios-row-card', function (event) {
        if ($(event.target).closest('.ios-gear-btn, .collapse').length) {
            return;
        }
        var did = this.getAttribute('data-did');
        if (did) {
            event.preventDefault();
            pycmd("open:" + did);
        }
    });
}

$(initDeckInteractions);

function handleDropEvent(event, ui) {
    var draggedDeckId = ui.draggable.attr('id');
    var ontoDeckId = $(this).attr('id') || '';

    pycmd("drag:" + draggedDeckId + "," + ontoDeckId);
}

function columnDropEvent(event, ui) {
    var draggedDeckId = ui.draggable.attr('colpos');
    var ontoDeckId = $(this).attr('colpos') || '';
    pycmd("dragColumn:" + draggedDeckId + "," + ontoDeckId);
}
