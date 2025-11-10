/*
 * Minimal JS helper that turns lines beginning with ">" into a Notion-style
 * toggle (<details> block) whenever space or enter is pressed.
 *
 * Compatible with Anki versions 2.1.41 and newer.
 */
 
var insert_symbols = new function () {
    const SETUP_TIMEOUT = 500;
    const KEY_BACKSPACE = "Backspace";
    const KEY_SPACE = " ";
    const KEY_ENTER = "Enter";
    const TOGGLE_TEMPLATE = '<details data-notion-toggle="1" open>\n  <summary data-notion-toggle-summary="1">&#8203;{summary}</summary>\n  <div data-notion-toggle-body><div data-notion-toggle-line><br></div></div>\n</details>';
    const BULLET_TEMPLATE = '<div data-notion-bullet="1"><ul><li data-notion-bullet-line="1">{bullet}</li></ul></div>';
    const ORDERED_TEMPLATE = '<div data-notion-ordered="1"><ol><li data-notion-ordered-line="1">{item}</li></ol></div>';
    const STYLE_TAG_ID = "notion-toggle-styles";
    const TOGGLE_CSS = `
details[data-notion-toggle] summary::-webkit-details-marker {
    display: none;
}
details[data-notion-toggle] summary {
    list-style: none;
    display: flex;
    align-items: center;
    gap: 0.35em;
    font-size: 0.95em;
    cursor: text;
    padding: 2px 0;
}
details[data-notion-toggle] summary::before {
    content: "▸";
    display: inline-block;
    width: 1em;
    text-align: center;
    font-size: 0.85em;
    cursor: pointer;
}
details[data-notion-toggle][open] summary::before {
    content: "▾";
}
details[data-notion-toggle] [data-notion-toggle-body] {
    margin: 4px 0;
    padding: 4px 6px 4px 1.15em;
    border-radius: 0;
    background: transparent;
    border-left: none;
    display: flex;
    flex-direction: column;
    gap: 0.25em;
    min-height: 1.4em;
}
details[data-notion-toggle] [data-notion-toggle-line] {
    min-height: 1.2em;
    padding: 2px 0;
}
div[data-notion-bullet],
div[data-notion-ordered] {
    margin: 0.2em 0;
}
div[data-notion-bullet] ul,
div[data-notion-ordered] ol {
    margin: 0 0 0 1.5em;
    padding-left: 0;
}
/* H1: Primary section title — large, bold, clear spacing */
[data-notion-heading="1"] {
    font-size: 1.6em;
    font-weight: 700;
    margin: 0.6em 0 0.3em;
    line-height: 1.3;
}
/* H2: Subsection heading — slightly smaller, balanced weight */
[data-notion-heading="2"] {
    font-size: 1.35em;
    font-weight: 600;
    margin: 0.5em 0 0.25em;
    line-height: 1.35;
}
/* H3: Inline or tertiary heading — compact but distinct */
[data-notion-heading="3"] {
    font-size: 1.15em;
    font-weight: 600;
    margin: 0.4em 0 0.2em;
    line-height: 1.4;
}
/* Adjacent text margin ensures comfortable vertical rhythm */
[data-notion-heading] + div,
[data-notion-heading] + p {
    margin-top: 0.25em;
}
`;

    const INSERT_BUILDERS = {
        toggle: (info) => buildToggleHtml(info.summary),
        bullet: (info) => buildBulletHtml(info.content),
        ordered: (info) => buildOrderedHtml(info.content),
        heading: (info) => buildHeadingHtml(info.level, info.content),
        youtube: (info) => buildYouTubeHtml(info.videoId),
    };

    const POST_INSERT_FOCUSERS = {
        toggle: (root, info) => focusLatestSummary(root, info.hasSummary),
        bullet: (root, info) => focusLatestBulletLine(root, info.hasContent),
        ordered: (root, info) => focusLatestOrderedLine(root, info.hasContent),
        heading: (root, info) => focusLatestHeading(root, info.hasContent),
        youtube: (root, info) => focusAfterInsertedBlock(root),
    };

    this.onKeyDown = function (evt) {
        const key = evt.key;

        if (evt.altKey && key === KEY_ENTER) {
            if (toggleCurrentDetails(evt)) {
                evt.preventDefault();
                evt.stopPropagation();
            }
            return;
        }
        if (key === KEY_BACKSPACE) {
            if (handleBackspaceInBody(evt) || handleBackspaceOnSummary(evt)) {
                return;
            }
        }
        if (evt.ctrlKey) {
            return;
        }
        if (key === KEY_ENTER) {
            if (handleEnterOnSummary(evt)) {
                return;
            }
            if (replaceToggleLine(evt)) {
                evt.preventDefault();
                evt.stopPropagation();
                return;
            }
        }
        if (key === KEY_SPACE) {
            if (replaceToggleLine(evt)) {
                evt.preventDefault();
                evt.stopPropagation();
            }
        }
    };

    this.onKeyUp = function () {};

    this.addListenersV1 = function () {
        injectStyles(document);
        forEditorField([], (field) => {
            if (!field.hasAttribute("has-type-symbols")) {
                field.editingArea.editable.addEventListener("keydown", this.onKeyDown);
                field.editingArea.editable.addEventListener("keyup", this.onKeyUp);
                field.setAttribute("has-type-symbols", "");
            }
            if (field.editingArea && field.editingArea.editable) {
                injectStyles(field.editingArea.editable.ownerDocument);
            }
        });
    };

    this.addListenersV2 = function () {
        setTimeout(() => {
            injectStyles(document);
            const editorFields = document.getElementsByClassName("rich-text-editable");
            for (const field of editorFields) {
                if (field.shadowRoot !== undefined) {
                    if (!field.hasAttribute("has-type-symbols")) {
                        field.shadowRoot.addEventListener("keydown", this.onKeyDown);
                        field.shadowRoot.addEventListener("keyup", this.onKeyUp);
                        field.setAttribute("has-type-symbols", "");
                    }
                    injectStyles(field.shadowRoot);
                }
            }
        }, SETUP_TIMEOUT);
    };

    if (typeof forEditorField !== "undefined") {
        this.addListenersV1();
    } else {
        this.addListenersV2();
    }

    function replaceToggleLine(evt) {
        const root = evt.currentTarget.getRootNode();
        const selection = getSelectionForRoot(root);
        if (!selection || !selection.isCollapsed) {
            return false;
        }

        if (evt && evt.key === KEY_ENTER && isSelectionInsideHeading(selection)) {
            return false;
        }

        const textInfo = getTextNodeAndOffsetFromSelection(selection);
        if (!textInfo) {
            return false;
        }
        const node = textInfo.node;
        const text = node.textContent || "";
        const cursorPos = textInfo.offset;
        const lineInfo = extractToggleInfo(text, cursorPos, evt && evt.key);

        if (!lineInfo || !INSERT_BUILDERS[lineInfo.kind]) {
            return false;
        }

        const html = INSERT_BUILDERS[lineInfo.kind](lineInfo);
        replaceTextWithHtml(
            root,
            selection,
            node,
            lineInfo.start,
            lineInfo.end,
            html,
            () => POST_INSERT_FOCUSERS[lineInfo.kind](root, lineInfo)
        );
        return true;
    }

    function handleEnterOnSummary(evt) {
        const root = evt.currentTarget.getRootNode();
        const selection = getSelectionForRoot(root);
        if (!selection || !selection.focusNode) {
            return false;
        }
        const summary = findSummaryAncestor(selection.focusNode);
        if (!summary) {
            return false;
        }
        const toggle = findToggleAncestor(summary);
        if (!toggle) {
            return false;
        }
        evt.preventDefault();
        evt.stopPropagation();

        if (toggle.open) {
            focusToggleBody(root, toggle);
        } else if (isSummaryEmpty(summary)) {
            removeEmptyToggleAndMoveBelowPrevious(root, toggle);
        } else {
            insertNewToggleBelow(root, toggle);
        }
        return true;
    }

    function extractToggleInfo(text, cursorPos, triggerKey) {
        if (!text || cursorPos < 0) {
            return null;
        }

        const lineStart = findLineStart(text, cursorPos);
        const markerIndex = skipSpaces(text, lineStart);
        if (markerIndex >= text.length || text[markerIndex] === "\n") {
            return null;
        }

        const marker = text[markerIndex];
        const lineEnd = findLineEnd(text, cursorPos);

        if (marker === ">") {
            const contentStart = skipSpaces(text, markerIndex + 1);
            const rawSummary = text.substring(contentStart, lineEnd);
            const summary = rawSummary.trim();
            return {
                kind: 'toggle',
                start: lineStart,
                end: lineEnd,
                summary: summary,
                hasSummary: summary.length > 0
            };
        }

        if (marker === "#") {
            let level = 1;
            let idx = markerIndex + 1;
            while (idx < text.length && text[idx] === "#" && level < 3) {
                level += 1;
                idx += 1;
            }
            if (idx < text.length && text[idx] === "#") {
                return null;
            }
            const hasActualSpace = idx < text.length && text[idx] === " ";
            const pendingSpace = triggerKey === KEY_SPACE && idx === cursorPos;
            if (!hasActualSpace && !pendingSpace) {
                return null;
            }
            const contentStart = skipSpaces(text, idx);
            const rawContent = text.substring(contentStart, lineEnd);
            const content = rawContent.trim();
            return {
                kind: 'heading',
                level: level,
                start: lineStart,
                end: lineEnd,
                content: content,
                hasContent: content.length > 0
            };
        }

        if (marker === "-") {
            const contentStart = skipSpaces(text, markerIndex + 1);
            const rawContent = text.substring(contentStart, lineEnd);
            const content = rawContent.trim();
            return {
                kind: 'bullet',
                start: lineStart,
                end: lineEnd,
                content: content,
                hasContent: content.length > 0
            };
        }

        if (marker === "1" && markerIndex + 1 < text.length && text[markerIndex + 1] === ".") {
            const afterMarker = markerIndex + 2;
            if (afterMarker < text.length && !/\s/.test(text[afterMarker])) {
                return null;
            }
            const contentStart = skipSpaces(text, afterMarker);
            const rawContent = text.substring(contentStart, lineEnd);
            const content = rawContent.trim();
            return {
                kind: 'ordered',
                start: lineStart,
                end: lineEnd,
                content: content,
                hasContent: content.length > 0
            };
        }

        const ytMatch = text.substring(markerIndex, lineEnd).match(/^https?:\/\/(www\.)?(youtube\.com\/watch\?v=|youtu\.be\/)([\w\-]+)/i);
        if (ytMatch) {
            const videoId = ytMatch[3];
            return {
                kind: 'youtube',
                start: lineStart,
                end: lineEnd,
                videoId: videoId
            };
        }

        return null;
    }

    function findLineStart(text, cursorPos) {
        for (let i = cursorPos - 1; i >= 0; i--) {
            if (text[i] === "\n") {
                return i + 1;
            }
        }
        return 0;
    }

    function findLineEnd(text, cursorPos) {
        for (let i = cursorPos; i < text.length; i++) {
            if (text[i] === "\n") {
                return i;
            }
        }
        return text.length;
    }

    function skipSpaces(text, index) {
        let i = index;
        while (i < text.length && /\s/.test(text[i]) && text[i] !== "\n") {
            i++;
        }
        return i;
    }

    function replaceTextWithHtml(root, selection, node, rangeStart, rangeEnd, html, afterInsert) {
        const doc = node.ownerDocument || document;
        const range = doc.createRange();
        range.setStart(node, rangeStart);
        range.setEnd(node, rangeEnd);
        selection.removeAllRanges();
        selection.addRange(range);

        const fragment = createFragmentFromHtml(range, doc, html);
        const lastInserted = fragment.lastChild;
        range.deleteContents();
        range.insertNode(fragment);

        const afterRange = doc.createRange();
        if (lastInserted) {
            afterRange.setStartAfter(lastInserted);
        } else {
            afterRange.setStart(range.endContainer, range.endOffset);
        }
        afterRange.collapse(true);
        selection.removeAllRanges();
        selection.addRange(afterRange);

        if (afterInsert) {
            afterInsert();
        }
    }

    function createFragmentFromHtml(range, doc, html) {
        if (range && range.createContextualFragment) {
            return range.createContextualFragment(html);
        }
        const template = doc.createElement("template");
        template.innerHTML = html;
        const fragment = doc.createDocumentFragment();
        while (template.content.firstChild) {
            fragment.appendChild(template.content.firstChild);
        }
        return fragment;
    }

    function buildHtml(template, placeholder, content, allowEmptyText) {
        const safeContent = content.length ? escapeHtml(content) : (allowEmptyText ? "" : "<br>");
        return template.replace(placeholder, safeContent);
    }

    function buildToggleHtml(summary) {
        return buildHtml(TOGGLE_TEMPLATE, "{summary}", summary, true);
    }

    function buildBulletHtml(content) {
        return buildHtml(BULLET_TEMPLATE, "{bullet}", content, false);
    }

    function buildOrderedHtml(content) {
        return buildHtml(ORDERED_TEMPLATE, "{item}", content, false);
    }

    function buildHeadingHtml(level, content) {
        const clampedLevel = Math.min(Math.max(level, 1), 3);
        const safeContent = content.length ? escapeHtml(content) : "&#8203;";
        return `<h${clampedLevel} data-notion-heading="${clampedLevel}">${safeContent}</h${clampedLevel}>`;
    }

    function buildYouTubeHtml(videoId) {
        const safeId = escapeHtml(videoId);
        return `
<div data-notion-before-youtube><br></div>
<div data-notion-youtube contenteditable="false">
  <div style="height:0;overflow:hidden;padding-top:56.25%;position:relative;width:100%;">
    <iframe
      style="position:absolute;top:0;left:0;width:100%;height:100%;"
      src="https://tube.rvere.com/embed?v=${safeId}"
      frameborder="0"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen>
    </iframe>
  </div>
</div>
<div data-notion-after-youtube><br></div>`;
    }

    function focusLatestSummary(root, hasSummary) {
        const summaries = querySelectorAll(root, "[data-notion-toggle-summary]");
        if (!summaries.length) {
            return;
        }
        focusSummaryElement(root, summaries[summaries.length - 1], hasSummary);
    }

    function focusLatestListLine(root, selector, hasContent) {
        const lines = querySelectorAll(root, selector);
        if (!lines.length) {
            return;
        }
        const line = lines[lines.length - 1];
        ensureListLinePlaceholder(line);
        const selection = getSelectionForRoot(root);
        if (!selection) {
            return;
        }
        const doc = line.ownerDocument || document;
        const range = doc.createRange();
        if (hasContent && line.lastChild && line.lastChild.nodeType === Node.TEXT_NODE) {
            range.setStart(line.lastChild, line.lastChild.textContent.length);
        } else {
            range.setStart(line, 0);
        }
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    function focusLatestBulletLine(root, hasContent) {
        focusLatestListLine(root, "[data-notion-bullet-line]", hasContent);
    }

    function focusLatestOrderedLine(root, hasContent) {
        focusLatestListLine(root, "[data-notion-ordered-line]", hasContent);
    }

    function focusLatestHeading(root, hasContent) {
        const headings = querySelectorAll(root, "[data-notion-heading]");
        if (!headings.length) {
            return;
        }
        focusHeadingElement(root, headings[headings.length - 1], hasContent);
    }

    function focusAfterInsertedBlock(root) {
        const placeholders = querySelectorAll(root, "[data-notion-after-youtube]");
        if (!placeholders.length) {
            return;
        }
        const placeholder = placeholders[placeholders.length - 1];
        const selection = getSelectionForRoot(root);
        if (!selection) {
            return;
        }
        const doc = placeholder.ownerDocument || document;
        const range = doc.createRange();
        range.selectNodeContents(placeholder);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    function getSelectionForRoot(root) {
        if (root && root.getSelection) {
        return root.getSelection();
        }
        if (document.getSelection) {
            return document.getSelection();
        }
        return window.getSelection();
    }

    function querySelectorAll(root, selector) {
        if (root && root.querySelectorAll) {
            return root.querySelectorAll(selector);
        }
        return document.querySelectorAll(selector);
    }

    function getTextNodeAndOffsetFromSelection(selection) {
        if (!selection || selection.rangeCount === 0) {
            return null;
        }
        const range = selection.getRangeAt(0);
        let node = range.startContainer;
        let offset = range.startOffset;

        if (node.nodeType !== Node.TEXT_NODE) {
            const child = node.childNodes[offset] || node.firstChild;
            if (child && child.nodeType === Node.TEXT_NODE) {
                node = child;
                offset = child.textContent.length;
            } else {
                return null;
            }
        }

        return { node, offset };
    }

    function focusSummaryElement(root, summary, collapseAtEnd) {
        const selection = getSelectionForRoot(root);
        if (!selection) {
            return;
        }
        const doc = summary.ownerDocument || document;
        const range = doc.createRange();

        if (collapseAtEnd) {
            range.selectNodeContents(summary);
            range.collapse(false);
        } else {
            const textNode = getSummaryTextNode(summary);
            if (textNode) {
                const offset = Math.min(textNode.textContent.length, 1);
                range.setStart(textNode, offset);
                range.collapse(true);
            } else {
                range.selectNodeContents(summary);
                range.collapse(true);
            }
        }

        selection.removeAllRanges();
        selection.addRange(range);
    }

    function focusHeadingElement(root, heading, collapseAtEnd) {
        const selection = getSelectionForRoot(root);
        if (!selection) {
            return;
        }
        const doc = heading.ownerDocument || document;
        const range = doc.createRange();
        range.selectNodeContents(heading);
        range.collapse(collapseAtEnd);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    function focusToggleBody(root, toggle) {
        const body = toggle.querySelector("[data-notion-toggle-body]");
        if (!body) {
            return;
        }
        toggle.open = true;
        const selection = getSelectionForRoot(root);
        if (!selection) {
            return;
        }
        const doc = body.ownerDocument || document;
        const line = ensureToggleBodyLine(body);
        const range = doc.createRange();
        range.selectNodeContents(line);
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    function insertNewToggleBelow(root, currentToggle) {
        const doc = currentToggle.ownerDocument || document;
        const container = doc.createElement("div");
        container.innerHTML = buildToggleHtml("");
        const newToggle = container.firstElementChild;
        if (!newToggle) {
            return;
        }

        newToggle.removeAttribute("open");
        newToggle.open = false;

        const parent = currentToggle.parentNode;
        if (!parent) {
            return;
        }
        parent.insertBefore(newToggle, currentToggle.nextSibling);

        const summary = newToggle.querySelector("[data-notion-toggle-summary]");
        if (summary) {
            focusSummaryElement(root, summary, false);
        }
    }

    function ensureToggleBodyLine(body) {
        observeBody(body);
        ensurePersistentLine(body);
        const doc = body.ownerDocument || document;
        const lines = body.querySelectorAll("[data-notion-toggle-line]");
        let line = lines.length ? lines[lines.length - 1] : null;
        if (!line) {
            line = createToggleLine(doc);
            body.appendChild(line);
            return line;
        }
        if (!line.textContent.trim()) {
            if (!line.lastChild) {
                line.appendChild(doc.createElement("br"));
            }
            return line;
        }
        const newLine = createToggleLine(doc);
        body.appendChild(newLine);
        return newLine;
    }

    function ensurePersistentLine(body) {
        if (!body) {
            return;
        }
        const doc = body.ownerDocument || document;
        const lines = body.querySelectorAll("[data-notion-toggle-line]");
        if (lines.length === 0) {
            body.appendChild(createToggleLine(doc));
        }
    }

    function observeBody(body) {
        if (!body || body.__notionToggleObserver) {
            ensurePersistentLine(body);
            return;
        }
        const observer = new MutationObserver(() => ensurePersistentLine(body));
        observer.observe(body, { childList: true });
        body.__notionToggleObserver = observer;
        ensurePersistentLine(body);
    }

    function createToggleLine(doc) {
        const line = doc.createElement("div");
        line.setAttribute("data-notion-toggle-line", "1");
        line.appendChild(doc.createElement("br"));
        return line;
    }

    function ensureListLinePlaceholder(line) {
        if (!line.lastChild) {
            line.appendChild((line.ownerDocument || document).createElement("br"));
        }
    }

    function handleBackspaceOnSummary(evt) {
        const root = evt.currentTarget.getRootNode();
        const selection = getSelectionForRoot(root);
        if (!selection || !selection.focusNode) {
            return false;
        }
        const summary = findSummaryAncestor(selection.focusNode);
        if (!summary) {
            return false;
        }
        if (!isCaretAtSummaryStart(summary, selection)) {
            return false;
        }
        const toggle = findToggleAncestor(summary);
        if (!toggle) {
            return false;
        }
        evt.preventDefault();
        evt.stopPropagation();
        removeToggleAndFocus(root, toggle);
        return true;
    }

    function isCaretAtSummaryStart(summary, selection) {
        if (!selection.isCollapsed || selection.rangeCount === 0) {
            return false;
        }
        const focusNode = selection.focusNode;
        if (focusNode !== summary && !summary.contains(focusNode)) {
            return false;
        }
        const doc = summary.ownerDocument || document;
        try {
            const range = doc.createRange();
            range.selectNodeContents(summary);
            range.setEnd(focusNode, selection.focusOffset);
            return range.collapsed;
        } catch (err) {
            return false;
        }
    }

    function removeToggleAndFocus(root, toggle) {
        const parent = toggle.parentNode;
        if (!parent) {
            return;
        }

        const previousSummary = findSiblingSummary(toggle, true);
        const nextSummary = findSiblingSummary(toggle, false);

        parent.removeChild(toggle);

        if (previousSummary) {
            focusSummaryElement(root, previousSummary, true);
        } else if (nextSummary) {
            focusSummaryElement(root, nextSummary, false);
        } else {
            focusFallbackPosition(root, parent);
        }
    }

    function findSiblingSummary(toggle, searchPrevious) {
        let node = searchPrevious ? toggle.previousElementSibling : toggle.nextElementSibling;
        while (node) {
            if (node.matches && node.matches("details[data-notion-toggle]")) {
                return node.querySelector("[data-notion-toggle-summary]");
            }
            node = searchPrevious ? node.previousElementSibling : node.nextElementSibling;
        }
        return null;
    }

    function focusFallbackPosition(root, container) {
        const doc = container.ownerDocument || document;
        let target = container.lastChild;
        if (!target || (target.nodeType === Node.ELEMENT_NODE && target.hasAttribute && target.hasAttribute("data-notion-toggle"))) {
            const placeholder = doc.createElement("div");
            placeholder.appendChild(doc.createElement("br"));
            container.appendChild(placeholder);
            target = placeholder;
        }
        const selection = getSelectionForRoot(root);
        if (!selection) {
            return;
        }
        const range = doc.createRange();
        range.selectNodeContents(target);
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    function handleBackspaceInBody(evt) {
        const root = evt.currentTarget.getRootNode();
        const selection = getSelectionForRoot(root);
        if (!selection || !selection.focusNode || !selection.isCollapsed || selection.rangeCount === 0) {
            return false;
        }

        const range = selection.getRangeAt(0);

        const listLine =
            findAncestorWithAttr(range.startContainer, "data-notion-bullet-line") ||
            findAncestorWithAttr(range.startContainer, "data-notion-ordered-line");

        if (listLine) {
            const doc = listLine.ownerDocument || document;
            const startRange = doc.createRange();
            startRange.setStart(listLine, 0);
            startRange.setEnd(range.startContainer, range.startOffset);
            const beforeText = startRange.toString().replace(/\u200B/g, "").trim();
            if (beforeText.length) {
                return false;
            }

            evt.preventDefault();
            evt.stopPropagation();

            const newLine = convertListLineToToggleLine(listLine);
            if (newLine) {
                const selection = getSelectionForRoot(root);
                if (selection) {
                    const focusRange = (newLine.ownerDocument || document).createRange();
                    focusRange.selectNodeContents(newLine);
                    focusRange.collapse(true);
                    selection.removeAllRanges();
                    selection.addRange(focusRange);
                }
            }
            return true;
        }

        const line = findAncestorWithAttr(range.startContainer, "data-notion-toggle-line");
        const body = line && findBodyAncestor(line);
        const toggle = body && findToggleAncestor(body);
        if (!line || !body || !toggle) {
            return false;
        }

        const bodyLines = body.querySelectorAll("[data-notion-toggle-line]");
        if (!bodyLines.length || bodyLines[0] !== line) {
            return false;
        }

        const doc = line.ownerDocument || document;
        const testRange = doc.createRange();
        testRange.setStart(line, 0);
        testRange.setEnd(range.startContainer, range.startOffset);
        const beforeText = testRange.toString().replace(/\u200B/g, "").trim();
        if (beforeText.length) {
            return false;
        }

        evt.preventDefault();
        evt.stopPropagation();

        observeBody(body);
        ensurePersistentLine(body);
        if (!line.lastChild) {
            line.appendChild(doc.createElement("br"));
        }

        const summary = toggle.querySelector("[data-notion-toggle-summary]");
        if (summary) {
            focusSummaryElement(root, summary, true);
        }
        return true;
    }

    function convertListLineToToggleLine(line) {
        if (!line) {
            return null;
        }
        const doc = line.ownerDocument || document;
        const list = line.parentNode;
        if (!list) {
            return null;
        }
        const wrapper = findAncestorWithAttr(line, "data-notion-bullet") || findAncestorWithAttr(line, "data-notion-ordered");
        const parent = wrapper ? wrapper.parentNode : list.parentNode;
        const newLine = doc.createElement("div");
        newLine.setAttribute("data-notion-toggle-line", "1");

        while (line.firstChild) {
            newLine.appendChild(line.firstChild);
        }
        if (!newLine.textContent.trim()) {
            newLine.appendChild(doc.createElement("br"));
        }

        if (!parent) {
            if (line.parentNode) {
                line.parentNode.replaceChild(newLine, line);
            }
            return newLine;
        }

        if (!wrapper) {
            if (line.parentNode) {
                line.parentNode.replaceChild(newLine, line);
            }
            return newLine;
        }

        const hasBeforeItems = !!line.previousElementSibling;
        const wrapperNextSibling = wrapper ? wrapper.nextSibling : null;

        let orderedNextStart = null;
        if (list.tagName && list.tagName.toLowerCase() === "ol") {
            const rawStart = parseInt(list.getAttribute("start") || "1", 10);
            const baseStart = Number.isNaN(rawStart) ? 1 : rawStart;
            let beforeCount = 0;
            for (let sibling = line.previousElementSibling; sibling; sibling = sibling.previousElementSibling) {
                beforeCount += 1;
            }
            orderedNextStart = baseStart + beforeCount + 1;
        }

        const afterNodes = [];
        for (let sibling = line.nextSibling; sibling; sibling = sibling.nextSibling) {
            afterNodes.push(sibling);
        }

        list.removeChild(line);

        let afterWrapper = null;
        if (afterNodes.length) {
            afterWrapper = doc.createElement("div");
            if (wrapper.hasAttribute("data-notion-bullet")) {
                afterWrapper.setAttribute("data-notion-bullet", "1");
            } else if (wrapper.hasAttribute("data-notion-ordered")) {
                afterWrapper.setAttribute("data-notion-ordered", "1");
            }
            const newList = doc.createElement(list.tagName.toLowerCase());
            if (orderedNextStart !== null) {
                newList.setAttribute("start", orderedNextStart);
            }
            afterWrapper.appendChild(newList);
            for (const node of afterNodes) {
                newList.appendChild(node);
            }
        }

        let wrapperRemoved = false;
        if (!list.firstChild && wrapper.parentNode === parent) {
            parent.removeChild(wrapper);
            wrapperRemoved = true;
        }

        const referenceForNewLine = (hasBeforeItems && !wrapperRemoved ? wrapper.nextSibling : wrapperNextSibling) || null;
        parent.insertBefore(newLine, referenceForNewLine);
        if (afterWrapper) {
            parent.insertBefore(afterWrapper, newLine.nextSibling);
        }
        return newLine;
    }

    function removeEmptyToggleAndMoveBelowPrevious(root, toggle) {
        const parent = toggle.parentNode;
        if (!parent) {
            return;
        }

        const next = toggle.nextSibling;
        parent.removeChild(toggle);

        const doc = parent.ownerDocument || document;
        const line = doc.createElement("div");
        line.appendChild(doc.createElement("br"));

        if (next) {
            parent.insertBefore(line, next);
        } else {
            parent.appendChild(line);
        }

        const selection = getSelectionForRoot(root);
        if (!selection) {
            return;
        }
        const range = doc.createRange();
        range.selectNodeContents(line);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    function injectStyles(target) {
        const root = target || document;
        if (!root) {
            return;
        }
        if (root.querySelector && root.querySelector(`#${STYLE_TAG_ID}`)) {
            return;
        }
        const doc = root.ownerDocument || root;
        const styleEl = doc.createElement("style");
        styleEl.id = STYLE_TAG_ID;
        styleEl.textContent = TOGGLE_CSS;
        if (root.head) {
            root.head.appendChild(styleEl);
        } else {
            root.appendChild(styleEl);
        }
    }

    function toggleCurrentDetails(evt) {
        const root = evt.currentTarget.getRootNode();
        const selection = getSelectionForRoot(root);
        if (!selection || !selection.focusNode) {
            return false;
        }
        const toggle = findToggleAncestor(selection.focusNode);
        if (!toggle) {
            return false;
        }
        toggle.open = !toggle.open;
        return true;
    }

    function findToggleAncestor(node) {
        return findAncestorWithAttr(node, "data-notion-toggle");
    }

    function findSummaryAncestor(node) {
        return findAncestorWithAttr(node, "data-notion-toggle-summary");
    }

    function findBodyAncestor(node) {
        return findAncestorWithAttr(node, "data-notion-toggle-body");
    }

    function findHeadingAncestor(node) {
        return findAncestorWithAttr(node, "data-notion-heading");
    }

    function findAncestorWithAttr(node, attr) {
        let current = node;
        while (current) {
            if (current.nodeType === Node.ELEMENT_NODE && current.hasAttribute(attr)) {
                return current;
            }
            current = current.parentNode;
        }
        return null;
    }

    function getSummaryTextNode(summary) {
        const doc = summary.ownerDocument || document;
        const walker = doc.createTreeWalker(summary, NodeFilter.SHOW_TEXT, null, false);
        return walker.nextNode();
    }

    function isSelectionInsideHeading(selection) {
        if (!selection || !selection.focusNode) {
            return false;
        }
        return !!findHeadingAncestor(selection.focusNode);
    }

    function isSummaryEmpty(summary) {
        const raw = (summary.textContent || "").replace(/\u200B/g, "").trim();
        return raw.length === 0;
    }

    function escapeHtml(str) {
        return str.replace(/[&<>\"']/g, function (ch) {
            switch (ch) {
                case "&":
                    return "&amp;";
                case "<":
                    return "&lt;";
                case ">":
                    return "&gt;";
                case '"':
                    return "&quot;";
                default:
                    return "&#39;";
            }
        });
    }
};
