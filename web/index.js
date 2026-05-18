import { app } from "../../scripts/app.js";

// 模块作用域：暴露给命令系统的入口
let _openExtensionManagerModal = null;

app.registerExtension({
    name: "KohowGia.ExtensionManager",

    // 注册命令（自动出现在 ComfyUI 设置 → 快捷键 中，可由用户自定义）
    commands: [
        {
            id: "KohowGia.ExtensionManager.Open",
            label: "打开扩展管理",
            function: () => { if (_openExtensionManagerModal) _openExtensionManagerModal(); }
        }
    ],

    // 默认快捷键 Ctrl+Alt+E（Alt 组合在 ComfyUI 内置中极少使用，避免冲突；用户可在设置中自定义）
    keybindings: [
        {
            combo: { key: "e", ctrl: true, alt: true },
            commandId: "KohowGia.ExtensionManager.Open"
        }
    ],

    async setup() {

        // ================= CSS 样式 =================
        const styleId = "kohowgia-extension-manager-styles";
        if (!document.getElementById(styleId)) {
            const style = document.createElement("style");
            style.id = styleId;
            style.textContent = `
                /* ===== KohowGia ExtensionManager ===== */

                /* —— 表头/表体 —— */
                .em-plugin-thead-wrap {
                    flex-shrink: 0; overflow: hidden;
                    background: #1a1a1a;
                    padding-right: 12px;
                    box-sizing: border-box;
                }
                .em-plugin-scroll {
                    flex: 1; min-height: 0;
                    overflow-x: hidden; overflow-y: scroll;
                }
                .em-plugin-scroll::-webkit-scrollbar { width: 12px; height: 12px; }
                .em-plugin-scroll::-webkit-scrollbar-track { background: #1a1a1a; }
                .em-plugin-scroll::-webkit-scrollbar-thumb {
                    background: #3a3a3a; border-radius: 6px;
                    border: 2px solid #1a1a1a;
                }
                .em-plugin-scroll::-webkit-scrollbar-thumb:hover { background: #4a4a4a; }
                .em-plugin-scroll::-webkit-scrollbar-corner { background: #1a1a1a; }

                .em-plugin-table {
                    border-collapse: separate; border-spacing: 0;
                    font-size: 12px;
                    table-layout: fixed;
                }
                .em-plugin-table th, .em-plugin-table td {
                    padding: 7px 8px; text-align: left;
                    border-bottom: 1px solid #2a2a2a;
                    white-space: nowrap;
                }
                .em-plugin-table th {
                    background: #1a1a1a; color: #888; font-weight: 600;
                }
                .em-plugin-table tr:hover td { background: #222; }
                .em-plugin-name { font-weight: 500; color: #ddd; overflow: hidden; text-overflow: ellipsis; }
                .em-plugin-remote { color: #666; overflow: hidden; text-overflow: ellipsis; }
                .em-plugin-commit { font-family: monospace; color: #888; font-size: 11px; }
                .em-plugin-actions { display: flex; gap: 4px; align-items: center; }
                .em-pending-dot {
                    display: inline-block; width: 6px; height: 6px;
                    background: #dc6; border-radius: 50%; margin-left: 6px;
                    vertical-align: middle;
                }

                /* —— 按钮 —— */
                .em-plugin-btn {
                    flex: 0 !important; padding: 0 7px !important; height: 24px !important;
                    font-size: 11px !important; white-space: nowrap;
                }
                .em-btn {
                    flex: 1; padding: 0; height: 30px; border: 1px solid #3a3a3a !important;
                    background: #2a2a2a !important; color: #fff !important;
                    border-radius: 5px; cursor: pointer; font-size: 12px; transition: 0.15s;
                    display: flex; justify-content: center; align-items: center;
                    font-family: inherit; box-sizing: border-box;
                }
                .em-btn:hover { background: #333 !important; color: #fff !important; border-color: #484848 !important; }
                .em-btn:disabled { opacity: 0.45; cursor: not-allowed; }
                .em-btn-danger { background: #4a1a1a !important; border-color: #6a2a2a !important; }
                .em-btn-danger:hover { background: #5a2020 !important; border-color: #884040 !important; }
                .em-btn-sm {
                    flex: none !important; height: 28px !important;
                    padding: 0 10px !important; font-size: 11px !important;
                }
                .em-btn-primary {
                    background: #1f4a6b !important; border-color: #2f6a8b !important;
                }
                .em-btn-primary:hover {
                    background: #2a5f88 !important; border-color: #3f7a9b !important;
                }
                .em-btn-warn {
                    background: #5a4800 !important; border-color: #7a6800 !important; color: #fff !important;
                    flex: none !important; height: 26px !important;
                    padding: 0 14px !important; font-size: 11px !important;
                    border-radius: 5px; cursor: pointer; transition: 0.15s;
                    display: flex; justify-content: center; align-items: center;
                    font-family: inherit; box-sizing: border-box;
                }
                .em-btn-warn:hover { background: #7a6800 !important; }

                /* —— Badge —— */
                .em-plugin-badge {
                    display: inline-block; padding: 1px 6px; border-radius: 3px;
                    font-size: 11px; font-weight: 500;
                }
                .em-badge-green  { background: #1a3a1a; color: #6c6; border: 1px solid #2a5a2a; }
                .em-badge-yellow { background: #3a2e00; color: #cc6; border: 1px solid #5a4800; }
                .em-badge-gray   { background: #2a2a2a; color: #777; border: 1px solid #3a3a3a; }

                /* —— 工具栏 —— */
                .em-header {
                    flex-shrink: 0; padding: 8px 10px;
                    border-bottom: 1px solid #2a2a2a;
                    display: flex; flex-direction: column; gap: 6px;
                }
                .em-toolbar {
                    display: flex; gap: 8px; align-items: center;
                }
                .em-tb-group {
                    display: flex; gap: 4px; align-items: center;
                }
                .em-tb-search { flex: 1; min-width: 180px; }
                .em-tb-divider {
                    width: 1px; height: 18px;
                    background: #3a3a3a; flex-shrink: 0;
                }
                .em-search-input {
                    width: 100%; height: 28px; padding: 0 10px;
                    background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 4px;
                    color: #ccc; font-size: 12px; font-family: inherit; outline: none;
                    box-sizing: border-box;
                }
                .em-search-input:focus { border-color: #4a4a4a; }

                /* —— 待重启黄条 —— */
                .em-pending-bar {
                    flex-shrink: 0; padding: 7px 12px;
                    background: #3a2e00; border-bottom: 1px solid #5a4800;
                    color: #dc6; font-size: 12px;
                    display: flex; align-items: center; justify-content: space-between; gap: 12px;
                }
                .em-pending-text b { color: #fc8; font-weight: 700; padding: 0 2px; }

                /* —— Toast —— */
                .em-toast-container {
                    position: fixed; top: 60px; right: 16px; z-index: 10100;
                    display: flex; flex-direction: column; gap: 8px;
                    pointer-events: none;
                }
                .em-toast {
                    min-width: 260px; max-width: 420px; padding: 10px 14px;
                    color: #ddd; border-radius: 6px;
                    font-size: 12px; line-height: 1.5;
                    display: flex; align-items: flex-start; gap: 10px;
                    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
                    pointer-events: auto; cursor: pointer;
                    opacity: 0; transform: translateX(20px);
                    transition: opacity 0.2s, transform 0.2s;
                }
                .em-toast.em-toast-in { opacity: 1; transform: translateX(0); }
                .em-toast-success { background: #1a3a1a; border: 1px solid #2a5a2a; }
                .em-toast-error   { background: #3a1a1a; border: 1px solid #5a2a2a; }
                .em-toast-warning { background: #3a2e00; border: 1px solid #5a4800; }
                .em-toast-info    { background: #1a2a3a; border: 1px solid #2a4060; }
                .em-toast-icon {
                    flex-shrink: 0; font-weight: 600; font-size: 13px;
                }
                .em-toast-success .em-toast-icon { color: #8c8; }
                .em-toast-error   .em-toast-icon { color: #f88; }
                .em-toast-warning .em-toast-icon { color: #dc6; }
                .em-toast-info    .em-toast-icon { color: #8af; }
                .em-toast-msg {
                    flex: 1; white-space: pre-wrap; word-break: break-word;
                }

                /* —— 上下文菜单 —— */
                .em-ctx-menu {
                    position: fixed; z-index: 10200;
                    background: #252525; border: 1px solid #3a3a3a; border-radius: 5px;
                    box-shadow: 0 6px 24px rgba(0,0,0,0.5);
                    padding: 4px; min-width: 140px; font-size: 12px; color: #ccc;
                }
                .em-ctx-item {
                    padding: 6px 10px; cursor: pointer; border-radius: 3px;
                    white-space: nowrap; user-select: none;
                }
                .em-ctx-item:hover { background: #333; }
                .em-ctx-item.em-ctx-danger { color: #f88; }
                .em-ctx-item.em-ctx-danger:hover { background: #3a1a1a; }
                .em-ctx-divider {
                    height: 1px; background: #3a3a3a; margin: 4px 0;
                }

                /* —— 通用 Dialog —— */
                .em-dialog-overlay {
                    position: fixed; inset: 0; z-index: 10050;
                    background: rgba(0,0,0,0.7);
                    display: flex; align-items: center; justify-content: center;
                }
                .em-dialog {
                    background: var(--comfy-menu-bg, #1e1e1e);
                    border: 1px solid #333; border-radius: 8px;
                    padding: 18px 22px; min-width: 340px; max-width: 600px; color: #ddd;
                    box-shadow: 0 8px 40px rgba(0,0,0,0.6);
                }
                .em-dialog-title {
                    font-size: 13px; font-weight: 600;
                    margin-bottom: 12px; color: #ddd;
                }
                .em-dialog-content {
                    font-size: 12px; color: #bbb;
                    margin-bottom: 18px; line-height: 1.6;
                }
                .em-dialog-content input[type="text"],
                .em-dialog-content textarea {
                    width: 100%; padding: 0 10px; height: 32px;
                    background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 5px;
                    color: #ccc; font-size: 12px; font-family: inherit; outline: none;
                    box-sizing: border-box;
                }
                .em-dialog-content input[type="text"]:focus { border-color: #4a4a4a; }
                .em-dialog-actions {
                    display: flex; gap: 8px; justify-content: flex-end;
                }
                .em-dialog-actions .em-btn {
                    flex: none !important; padding: 0 16px !important; height: 30px !important;
                }
            `;
            document.head.appendChild(style);
        }

        // ================= 通用工具：HTML 转义 =================
        function _escapeHtml(s) {
            return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
                "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
            }[c]));
        }

        // ================= Toast 系统 =================
        let _toastContainer = null;
        function _getToastContainer() {
            if (!_toastContainer || !document.body.contains(_toastContainer)) {
                _toastContainer = document.createElement("div");
                _toastContainer.className = "em-toast-container";
                document.body.appendChild(_toastContainer);
            }
            return _toastContainer;
        }
        const _toastIcons = { success: "✓", error: "✗", warning: "⚠", info: "ℹ" };
        function showToast({ type = "info", msg = "", duration = 4000 } = {}) {
            const container = _getToastContainer();
            const toast = document.createElement("div");
            toast.className = `em-toast em-toast-${type}`;
            const icon = _toastIcons[type] || _toastIcons.info;
            toast.innerHTML = `<span class="em-toast-icon"></span><span class="em-toast-msg"></span>`;
            toast.querySelector(".em-toast-icon").textContent = icon;
            toast.querySelector(".em-toast-msg").textContent  = String(msg || "");
            container.appendChild(toast);
            requestAnimationFrame(() => toast.classList.add("em-toast-in"));
            let dismissed = false;
            const dismiss = () => {
                if (dismissed) return;
                dismissed = true;
                toast.classList.remove("em-toast-in");
                setTimeout(() => toast.remove(), 220);
            };
            toast.onclick = dismiss;
            if (duration > 0) setTimeout(dismiss, duration);
            return { dismiss };
        }

        // ================= 通用 Dialog =================
        function showCustomDialog({ title = "", contentHTML = "", buttons = [], onMount = null } = {}) {
            return new Promise((resolve) => {
                const overlay = document.createElement("div");
                overlay.className = "em-dialog-overlay";
                const dialog = document.createElement("div");
                dialog.className = "em-dialog";
                const titleEl = document.createElement("div");
                titleEl.className = "em-dialog-title";
                titleEl.textContent = title;
                const contentEl = document.createElement("div");
                contentEl.className = "em-dialog-content";
                contentEl.innerHTML = contentHTML;
                const actionsEl = document.createElement("div");
                actionsEl.className = "em-dialog-actions";

                dialog.appendChild(titleEl);
                dialog.appendChild(contentEl);
                dialog.appendChild(actionsEl);
                overlay.appendChild(dialog);
                document.body.appendChild(overlay);

                let resolved = false;
                const cleanup = (value) => {
                    if (resolved) return;
                    resolved = true;
                    document.removeEventListener("keydown", onKey);
                    overlay.remove();
                    resolve(value);
                };

                for (const b of buttons) {
                    const btn = document.createElement("button");
                    btn.className = "em-btn"
                        + (b.danger  ? " em-btn-danger"  : "")
                        + (b.primary ? " em-btn-primary" : "");
                    btn.textContent = b.label;
                    btn.onclick = () => {
                        const v = (typeof b.value === "function") ? b.value(contentEl, dialog) : b.value;
                        cleanup(v);
                    };
                    actionsEl.appendChild(btn);
                }

                overlay.addEventListener("click", (e) => {
                    if (e.target === overlay) cleanup(null);
                });
                const onKey = (e) => { if (e.key === "Escape") cleanup(null); };
                document.addEventListener("keydown", onKey);

                if (typeof onMount === "function") onMount(contentEl, dialog);
                const firstInput = contentEl.querySelector("input,textarea,select");
                if (firstInput) requestAnimationFrame(() => firstInput.focus());
            });
        }

        async function showConfirm({ title = "确认", message = "", hint = "", okText = "确定", cancelText = "取消", danger = false } = {}) {
            const html = `
                <div style="white-space:pre-wrap;line-height:1.6;">${_escapeHtml(message)}</div>
                ${hint ? `<div style="margin-top:10px;font-size:11px;color:#888;line-height:1.5;">${_escapeHtml(hint)}</div>` : ""}
            `;
            const v = await showCustomDialog({
                title,
                contentHTML: html,
                buttons: [
                    { label: cancelText, value: false },
                    { label: okText, value: true, danger, primary: !danger },
                ]
            });
            return v === true;
        }

        // ================= Context Menu =================
        function showContextMenu(event, items) {
            if (event && event.preventDefault) event.preventDefault();
            document.querySelectorAll(".em-ctx-menu").forEach(el => el.remove());

            const menu = document.createElement("div");
            menu.className = "em-ctx-menu";
            for (const item of items) {
                if (item.divider) {
                    const sep = document.createElement("div");
                    sep.className = "em-ctx-divider";
                    menu.appendChild(sep);
                    continue;
                }
                const it = document.createElement("div");
                it.className = "em-ctx-item" + (item.danger ? " em-ctx-danger" : "");
                it.textContent = item.label;
                it.onclick = (e) => {
                    e.stopPropagation();
                    cleanup();
                    if (item.action) item.action();
                };
                menu.appendChild(it);
            }
            document.body.appendChild(menu);

            const rect = menu.getBoundingClientRect();
            let x = event.clientX, y = event.clientY;
            if (x + rect.width  > window.innerWidth)  x = window.innerWidth  - rect.width  - 8;
            if (y + rect.height > window.innerHeight) y = window.innerHeight - rect.height - 8;
            if (x < 4) x = 4;
            if (y < 4) y = 4;
            menu.style.left = x + "px";
            menu.style.top  = y + "px";

            const onKey = (e) => { if (e.key === "Escape") cleanup(); };
            const cleanup = () => {
                menu.remove();
                document.removeEventListener("click", cleanup);
                document.removeEventListener("contextmenu", cleanup);
                document.removeEventListener("keydown", onKey);
            };
            requestAnimationFrame(() => {
                document.addEventListener("click", cleanup);
                document.addEventListener("contextmenu", cleanup);
                document.addEventListener("keydown", onKey);
            });
        }

        // ================= 列宽拖拽（双表版）=================
        function _setupResizableTable(headerWrap, scrollWrap, storageKey) {
            const headerTable = headerWrap.querySelector("table");
            const bodyTable   = scrollWrap.querySelector("table");
            const headerCols  = Array.from(headerTable.querySelectorAll("col"));
            const bodyCols    = Array.from(bodyTable.querySelectorAll("col"));
            const ths         = Array.from(headerTable.querySelectorAll("thead th"));

            let saved = {};
            try { saved = JSON.parse(localStorage.getItem(storageKey) || "{}"); } catch (_) {}

            const widthOf = (col) => {
                const v = parseInt(col.style.width, 10);
                return (!isNaN(v) && v > 0) ? v : 100;
            };

            headerCols.forEach((col, idx) => {
                if (saved[idx]) {
                    col.style.width = saved[idx] + "px";
                    if (bodyCols[idx]) bodyCols[idx].style.width = saved[idx] + "px";
                }
            });

            const applyTotal = () => {
                let total = 0;
                headerCols.forEach(c => { total += widthOf(c); });
                headerTable.style.width = total + "px";
                bodyTable.style.width   = total + "px";
            };
            applyTotal();

            scrollWrap.addEventListener("scroll", () => {
                headerWrap.scrollLeft = scrollWrap.scrollLeft;
            });

            ths.forEach((th, idx) => {
                th.style.position = "relative";
                if (idx === ths.length - 1) return;

                const resizer = document.createElement("div");
                resizer.style.cssText = [
                    "position:absolute;right:0;top:0;",
                    "width:6px;height:100%;",
                    "cursor:col-resize;user-select:none;z-index:2;"
                ].join("");
                resizer.onmouseenter = () => { resizer.style.background = "rgba(255,255,255,0.18)"; };
                resizer.onmouseleave = () => { resizer.style.background = ""; };
                th.appendChild(resizer);

                resizer.addEventListener("mousedown", (e) => {
                    const startX     = e.pageX;
                    const startWidth = widthOf(headerCols[idx]);
                    const startTotal = parseInt(headerTable.style.width, 10) || 0;
                    document.body.style.cursor = "col-resize";
                    document.body.style.userSelect = "none";

                    const onMove = (ev) => {
                        const delta = ev.pageX - startX;
                        const newWidth = Math.max(40, startWidth + delta);
                        headerCols[idx].style.width = newWidth + "px";
                        if (bodyCols[idx]) bodyCols[idx].style.width = newWidth + "px";
                        const newTotal = startTotal + (newWidth - startWidth);
                        headerTable.style.width = newTotal + "px";
                        bodyTable.style.width   = newTotal + "px";
                    };
                    const onUp = () => {
                        document.removeEventListener("mousemove", onMove);
                        document.removeEventListener("mouseup", onUp);
                        document.body.style.cursor = "";
                        document.body.style.userSelect = "";
                        const widths = {};
                        headerCols.forEach((c, i) => { widths[i] = widthOf(c); });
                        try { localStorage.setItem(storageKey, JSON.stringify(widths)); } catch (_) {}
                    };
                    document.addEventListener("mousemove", onMove);
                    document.addEventListener("mouseup", onUp);
                    e.preventDefault();
                });
            });
        }

        // ================= 列宽拖拽（单表版，用于版本切换弹窗）=================
        function _makeColumnsResizable(table, storageKey) {
            const ths = Array.from(table.querySelectorAll("thead th"));
            let saved = {};
            try { saved = JSON.parse(localStorage.getItem(storageKey) || "{}"); } catch (_) {}

            const widthOf = (th) => {
                const inline = parseInt(th.style.width, 10);
                if (!isNaN(inline) && inline > 0) return inline;
                return th.offsetWidth || 100;
            };

            ths.forEach((th, idx) => {
                if (saved[idx]) th.style.width = saved[idx] + "px";
            });

            const recomputeTotal = () => {
                let total = 0;
                ths.forEach(t => { total += widthOf(t); });
                table.style.width = total + "px";
                table.style.minWidth = total + "px";
            };
            recomputeTotal();

            ths.forEach((th, idx) => {
                th.style.position = "relative";
                if (idx === ths.length - 1) return;

                const resizer = document.createElement("div");
                resizer.style.cssText = [
                    "position:absolute;right:0;top:0;",
                    "width:6px;height:100%;",
                    "cursor:col-resize;user-select:none;z-index:2;"
                ].join("");
                resizer.onmouseenter = () => { resizer.style.background = "rgba(255,255,255,0.18)"; };
                resizer.onmouseleave = () => { resizer.style.background = ""; };
                th.appendChild(resizer);

                resizer.addEventListener("mousedown", (e) => {
                    const startX          = e.pageX;
                    const startColWidth   = widthOf(th);
                    const startTableWidth = parseInt(table.style.width, 10) || table.offsetWidth;
                    document.body.style.cursor = "col-resize";
                    document.body.style.userSelect = "none";

                    const onMove = (ev) => {
                        const delta = ev.pageX - startX;
                        const newColWidth = Math.max(40, startColWidth + delta);
                        const actualDelta = newColWidth - startColWidth;
                        th.style.width = newColWidth + "px";
                        const newTableWidth = startTableWidth + actualDelta;
                        table.style.width    = newTableWidth + "px";
                        table.style.minWidth = newTableWidth + "px";
                    };
                    const onUp = () => {
                        document.removeEventListener("mousemove", onMove);
                        document.removeEventListener("mouseup", onUp);
                        document.body.style.cursor = "";
                        document.body.style.userSelect = "";
                        const widths = {};
                        ths.forEach((t, i) => { widths[i] = widthOf(t); });
                        try { localStorage.setItem(storageKey, JSON.stringify(widths)); } catch (_) {}
                    };
                    document.addEventListener("mousemove", onMove);
                    document.addEventListener("mouseup", onUp);
                    e.preventDefault();
                });
            });
        }

        // ================= 版本切换弹窗 =================
        let _versionModalEl = null;
        function _ensureVersionModal() {
            if (_versionModalEl) return _versionModalEl;

            const overlay = document.createElement("div");
            overlay.id = "em-version-modal";
            overlay.style.cssText = [
                "position:fixed;inset:0;z-index:10000;",
                "background:rgba(0,0,0,0.7);",
                "display:none;align-items:center;justify-content:center;"
            ].join("");

            const dialog = document.createElement("div");
            dialog.style.cssText = [
                "width:75vw;max-width:900px;height:78vh;",
                "background:var(--comfy-menu-bg,#1e1e1e);",
                "border-radius:8px;border:1px solid #333;",
                "display:flex;flex-direction:column;overflow:hidden;",
                "box-shadow:0 8px 40px rgba(0,0,0,0.6);"
            ].join("");

            const titleBar = document.createElement("div");
            titleBar.style.cssText = [
                "flex-shrink:0;padding:10px 16px;",
                "border-bottom:1px solid #2a2a2a;background:#1a1a1a;",
                "display:flex;align-items:center;justify-content:space-between;"
            ].join("");
            titleBar.innerHTML = `
                <span id="em-version-title" style="font-size:13px;font-weight:600;color:#ddd;">版本切换</span>
                <button id="em-version-close" style="background:none;border:none;color:#666;cursor:pointer;font-size:18px;line-height:1;padding:2px 8px;font-family:inherit;">✕</button>
            `;

            const scrollWrap = document.createElement("div");
            scrollWrap.className = "em-plugin-scroll";
            scrollWrap.style.cssText = "flex:1;min-height:0;overflow-x:auto;overflow-y:scroll;padding:0;";
            scrollWrap.innerHTML = `
                <table class="em-plugin-table" style="width:auto;">
                    <thead>
                        <tr>
                            <th style="width:80px;">版本 ID</th>
                            <th style="width:520px;">更新内容</th>
                            <th style="width:140px;">日期</th>
                            <th style="width:50px;text-align:center;">当前</th>
                            <th style="width:80px;"></th>
                        </tr>
                    </thead>
                    <tbody id="em-version-tbody"></tbody>
                </table>
            `;

            dialog.appendChild(titleBar);
            dialog.appendChild(scrollWrap);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            _makeColumnsResizable(scrollWrap.querySelector(".em-plugin-table"), "em_version_col_widths");

            const closeModal = () => { overlay.style.display = "none"; };
            const closeBtn = titleBar.querySelector("#em-version-close");
            closeBtn.onmouseover = () => { closeBtn.style.color = "#ccc"; };
            closeBtn.onmouseout  = () => { closeBtn.style.color = "#666"; };
            closeBtn.onclick = closeModal;
            overlay.addEventListener("click", (e) => { if (e.target === overlay) closeModal(); });

            _versionModalEl = overlay;
            return overlay;
        }

        async function openVersionModal(pluginName, onSwitch) {
            const overlay = _ensureVersionModal();
            const tbody   = overlay.querySelector("#em-version-tbody");
            const title   = overlay.querySelector("#em-version-title");

            title.textContent = `版本切换 · ${pluginName}`;
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:#666;">加载中…</td></tr>`;
            overlay.style.display = "flex";

            try {
                const res  = await fetch(`/extension_manager/plugins/commits?name=${encodeURIComponent(pluginName)}`);
                const data = await res.json();
                const { commits, current } = data;

                if (!commits || !commits.length) {
                    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:#666;">无提交记录（可能需要先 fetch）</td></tr>`;
                    return;
                }

                tbody.innerHTML = "";
                for (const c of commits) {
                    const isCurrent = current && (current.startsWith(c.hash) || c.hash.startsWith(current));
                    const tr = document.createElement("tr");
                    if (isCurrent) tr.style.background = "#1a2a1a";
                    tr.innerHTML = `
                        <td class="em-plugin-commit">${_escapeHtml(c.short)}</td>
                        <td style="max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#ccc;"
                            title="${_escapeHtml(c.message)}">${_escapeHtml(c.message)}</td>
                        <td style="color:#888;font-size:11px;white-space:nowrap;">${_escapeHtml(c.date)}</td>
                        <td style="text-align:center;">${isCurrent ? '<span style="color:#6c6;font-size:15px;">✓</span>' : ''}</td>
                        <td></td>
                    `;
                    if (!isCurrent) {
                        const btn = document.createElement("button");
                        btn.className = "em-btn em-plugin-btn";
                        btn.textContent = "切换";
                        btn.onclick = async () => {
                            btn.disabled = true; btn.textContent = "切换中…";
                            try {
                                const r = await fetch("/extension_manager/plugins/checkout", {
                                    method: "POST",
                                    headers: {"Content-Type": "application/json"},
                                    body: JSON.stringify({name: pluginName, ref: c.hash})
                                });
                                const j = await r.json();
                                if (j.status === "success") {
                                    overlay.style.display = "none";
                                    showToast({ type: "success", msg: `${pluginName} 已切换到 ${c.short}` });
                                    if (onSwitch) onSwitch(pluginName);
                                } else {
                                    showToast({ type: "error", msg: `切换失败: ${j.msg}` });
                                    btn.disabled = false; btn.textContent = "切换";
                                }
                            } catch (e) {
                                showToast({ type: "error", msg: "请求失败: " + e });
                                btn.disabled = false; btn.textContent = "切换";
                            }
                        };
                        tr.querySelector("td:last-child").appendChild(btn);
                    }
                    tbody.appendChild(tr);
                }
            } catch (e) {
                tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#f66;">加载失败: ${_escapeHtml(String(e))}</td></tr>`;
            }
        }

        // ================= 插件管理面板 =================
        function createPluginsPanel(container) {
            container.innerHTML = `
                <div class="em-header">
                    <div class="em-toolbar">
                        <div class="em-tb-group em-tb-search">
                            <input type="text" class="em-search-input" id="em-search-input"
                                   placeholder="🔍 搜索插件名 / 远端地址..."/>
                        </div>
                        <div class="em-tb-divider"></div>
                        <div class="em-tb-group">
                            <button class="em-btn em-btn-sm" id="em-plugin-refresh">刷新</button>
                            <button class="em-btn em-btn-sm" id="em-plugin-check">检查更新</button>
                        </div>
                        <div class="em-tb-divider"></div>
                        <div class="em-tb-group">
                            <button class="em-btn em-btn-sm" id="em-plugin-update-all">一键更新</button>
                        </div>
                        <div class="em-tb-divider"></div>
                        <div class="em-tb-group">
                            <button class="em-btn em-btn-sm em-btn-primary" id="em-plugin-install-btn">安装</button>
                            <button class="em-btn em-btn-sm" id="em-plugin-export" title="将当前所有插件导出为 JSON 清单文件，用于跨机器同步">导出</button>
                            <button class="em-btn em-btn-sm" id="em-plugin-import" title="从 JSON 清单文件批量安装插件">导入</button>
                        </div>
                    </div>
                </div>
                <div class="em-pending-bar" id="em-pending-bar" style="display:none;">
                    <span class="em-pending-text">⚠ <b id="em-pending-count">0</b> 项改动等待重启生效</span>
                    <button class="em-btn-warn" id="em-pending-reboot">立即重启</button>
                </div>
                <div class="em-plugin-thead-wrap">
                    <table class="em-plugin-table" id="em-plugin-thead-table">
                        <colgroup>
                            <col style="width:40px;">
                            <col style="width:240px;">
                            <col style="width:320px;">
                            <col style="width:80px;">
                            <col style="width:80px;">
                            <col style="width:140px;">
                            <col style="width:90px;">
                            <col style="width:140px;">
                        </colgroup>
                        <thead>
                            <tr>
                                <th style="text-align:center;">启用</th>
                                <th>插件名</th>
                                <th>远端地址</th>
                                <th>分支</th>
                                <th>版本</th>
                                <th>更新时间</th>
                                <th>状态</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                    </table>
                </div>
                <div class="em-plugin-scroll">
                    <table class="em-plugin-table" id="em-plugin-tbody-table">
                        <colgroup>
                            <col style="width:40px;">
                            <col style="width:240px;">
                            <col style="width:320px;">
                            <col style="width:80px;">
                            <col style="width:80px;">
                            <col style="width:140px;">
                            <col style="width:90px;">
                            <col style="width:140px;">
                        </colgroup>
                        <tbody id="em-plugin-tbody"></tbody>
                    </table>
                </div>
            `;

            const tbody         = container.querySelector("#em-plugin-tbody");
            const btnRefresh    = container.querySelector("#em-plugin-refresh");
            const btnCheck      = container.querySelector("#em-plugin-check");
            const btnUpdateAll  = container.querySelector("#em-plugin-update-all");
            const btnInstallBtn = container.querySelector("#em-plugin-install-btn");
            const btnExport     = container.querySelector("#em-plugin-export");
            const btnImport     = container.querySelector("#em-plugin-import");
            const btnReboot     = container.querySelector("#em-pending-reboot");
            const searchInput   = container.querySelector("#em-search-input");
            const headerWrap    = container.querySelector(".em-plugin-thead-wrap");
            const scrollWrap    = container.querySelector(".em-plugin-scroll");
            const pendingBar    = container.querySelector("#em-pending-bar");
            const pendingCount  = container.querySelector("#em-pending-count");

            _setupResizableTable(headerWrap, scrollWrap, "em_plugin_col_widths");

            // —— 面板内部状态 ——
            let _lastPluginList = [];
            let _searchTerm = "";
            const _pendingRestart = new Set();

            // —— 待重启状态管理 ——
            function markPendingRestart(name) {
                if (!name) return;
                _pendingRestart.add(name);
                updatePendingBar();
                // 重渲染当前列表以显示小圆点
                renderTable(_lastPluginList);
            }
            function updatePendingBar() {
                if (_pendingRestart.size === 0) {
                    pendingBar.style.display = "none";
                } else {
                    pendingBar.style.display = "flex";
                    pendingCount.textContent = String(_pendingRestart.size);
                }
            }

            // —— 立即重启（绕开 ComfyUI-Manager 的 Restart/Stop 按钮状态机 bug）——
            async function rebootComfyUI() {
                const ok = await showConfirm({
                    title: "立即重启 ComfyUI?",
                    message: `${_pendingRestart.size} 项改动等待生效。`,
                    hint: "请先保存未保存的工作流。重启过程约 10-30 秒。",
                    okText: "重启",
                    danger: true,
                });
                if (!ok) return;
                showToast({
                    type: "info",
                    msg: "正在重启 ComfyUI...\n服务恢复后请刷新页面（Ctrl+Shift+R）。",
                    duration: 10000,
                });
                try {
                    await fetch("/manager/reboot", { method: "POST" });
                } catch (_) {
                    // 重启后连接断开是正常的
                }
            }

            // —— 工具函数 ——
            function statusBadge(p) {
                if (!p.is_git)              return `<span class="em-plugin-badge em-badge-gray">非git</span>`;
                if (p.has_update)           return `<span class="em-plugin-badge em-badge-yellow">有更新</span>`;
                if (p.has_update === false) return `<span class="em-plugin-badge em-badge-green">最新</span>`;
                return `<span class="em-plugin-badge em-badge-gray">未检查</span>`;
            }

            // git pull "Already up to date." 兼容旧版 git "Already up-to-date."
            const _NO_CHANGE_RE = /already up[ -]?to[ -]?date/i;

            // —— 单插件操作 ——
            async function togglePlugin(p, chk) {
                chk.disabled = true;
                try {
                    const res  = await fetch("/extension_manager/plugins/toggle", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({name: p.name})
                    });
                    const json = await res.json();
                    if (json.status === "success") {
                        markPendingRestart(p.display_name || p.name);
                        showToast({
                            type: "success",
                            msg: `${p.display_name || p.name} 已${chk.checked ? "启用" : "禁用"}`
                        });
                        loadPlugins(false);
                    } else {
                        showToast({ type: "error", msg: `操作失败: ${json.msg}` });
                        chk.checked = !chk.checked;
                        chk.disabled = false;
                    }
                } catch (e) {
                    showToast({ type: "error", msg: "请求失败: " + e });
                    chk.checked = !chk.checked;
                    chk.disabled = false;
                }
            }

            async function updatePlugin(p, btn) {
                btn.disabled = true;
                const oldText = btn.textContent;
                btn.textContent = "更新中…";
                try {
                    const res  = await fetch("/extension_manager/plugins/update", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({name: p.name})
                    });
                    const json = await res.json();
                    if (json.status === "success") {
                        const output = (json.output || "").trim();
                        const noChange = !output || _NO_CHANGE_RE.test(output);
                        if (noChange) {
                            showToast({ type: "info", msg: `${p.display_name || p.name} 已是最新` });
                        } else {
                            markPendingRestart(p.display_name || p.name);
                            showToast({ type: "success", msg: `${p.display_name || p.name} 已更新` });
                        }
                        loadPlugins(false);
                    } else {
                        showToast({ type: "error", msg: `更新失败: ${json.msg}` });
                        btn.disabled = false;
                        btn.textContent = oldText;
                    }
                } catch (e) {
                    showToast({ type: "error", msg: "请求失败: " + e });
                    btn.disabled = false;
                    btn.textContent = oldText;
                }
            }

            async function repairPlugin(p, clean) {
                const title   = clean ? "确认重装?" : "确认修复?";
                const message = clean
                    ? `重装 "${p.display_name || p.name}" 将恢复到远端版本，并删除本地额外文件（包括 .gitignore 忽略的文件）。`
                    : `修复 "${p.display_name || p.name}" 将恢复缺失或被修改的仓库文件，但保留本地额外文件。`;
                const ok = await showConfirm({
                    title, message,
                    okText: clean ? "重装" : "修复",
                    danger: clean,
                });
                if (!ok) return;

                const inProgressToast = showToast({
                    type: "info",
                    msg: `正在${clean ? "重装" : "修复"} ${p.display_name || p.name}...`,
                    duration: 0,
                });
                try {
                    const res = await fetch("/extension_manager/plugins/repair", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({name: p.name, clean})
                    });
                    const text = await res.text();
                    let json;
                    try { json = JSON.parse(text); }
                    catch (_) { throw new Error(text || `HTTP ${res.status}`); }

                    inProgressToast.dismiss();
                    if (json.status === "success") {
                        markPendingRestart(p.display_name || p.name);
                        showToast({
                            type: "success",
                            msg: `${p.display_name || p.name} ${clean ? "重装" : "修复"}完成`
                        });
                        loadPlugins(false);
                    } else {
                        showToast({ type: "error", msg: `${clean ? "重装" : "修复"}失败: ${json.msg}` });
                    }
                } catch (e) {
                    inProgressToast.dismiss();
                    showToast({ type: "error", msg: "请求失败: " + e });
                }
            }

            async function uninstallPlugin(p) {
                const ok = await showConfirm({
                    title: `卸载 "${p.display_name || p.name}"?`,
                    message: "此操作不可恢复。",
                    hint: "插件目录将被删除，重启后生效。",
                    okText: "卸载",
                    danger: true,
                });
                if (!ok) return;
                try {
                    const res  = await fetch("/extension_manager/plugins/uninstall", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({name: p.name})
                    });
                    const json = await res.json();
                    if (json.status === "success") {
                        markPendingRestart(p.display_name || p.name);
                        showToast({ type: "success", msg: `${p.display_name || p.name} 已卸载` });
                        loadPlugins(false);
                    } else {
                        showToast({ type: "error", msg: `卸载失败: ${json.msg}` });
                    }
                } catch (e) {
                    showToast({ type: "error", msg: "请求失败: " + e });
                }
            }

            // —— 渲染列表 ——
            function renderTable(plugins) {
                const term = _searchTerm;
                const filtered = term
                    ? plugins.filter(p => {
                        const name = (p.display_name || p.name || "").toLowerCase();
                        const remote = (p.remote || "").toLowerCase();
                        return name.includes(term) || remote.includes(term);
                    })
                    : plugins;

                tbody.innerHTML = "";
                if (filtered.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px;color:#666;">${term ? "无匹配插件" : "暂无插件"}</td></tr>`;
                    return;
                }

                for (const p of filtered) {
                    const tr = document.createElement("tr");
                    if (!p.enabled) tr.style.opacity = "0.5";
                    const displayName = p.display_name || p.name;
                    const isPending = _pendingRestart.has(displayName);

                    tr.innerHTML = `
                        <td style="text-align:center;"></td>
                        <td class="em-plugin-name" title="${_escapeHtml(p.name)}">
                            ${_escapeHtml(displayName)}${isPending ? '<span class="em-pending-dot" title="待重启生效"></span>' : ''}
                        </td>
                        <td class="em-plugin-remote" title="${_escapeHtml(p.remote || "")}">${_escapeHtml(p.remote || "-")}</td>
                        <td>${_escapeHtml(p.branch || "-")}</td>
                        <td class="em-plugin-commit">${_escapeHtml(p.commit || "-")}</td>
                        <td>${p.date ? _escapeHtml(p.date.slice(0, 16)) : "-"}</td>
                        <td>${statusBadge(p)}</td>
                        <td class="em-plugin-actions"></td>
                    `;

                    const chk = document.createElement("input");
                    chk.type = "checkbox";
                    chk.checked = !!p.enabled;
                    chk.title = p.enabled ? "点击禁用（重启生效）" : "点击启用（重启生效）";
                    chk.style.cursor = "pointer";
                    chk.onchange = () => togglePlugin(p, chk);
                    tr.querySelector("td:first-child").appendChild(chk);

                    const actions = tr.querySelector(".em-plugin-actions");

                    if (p.is_git) {
                        // 主操作：更新
                        const btnUpdate = document.createElement("button");
                        btnUpdate.className = "em-btn em-plugin-btn";
                        btnUpdate.textContent = "更新";
                        btnUpdate.onclick = (e) => {
                            e.stopPropagation();
                            updatePlugin(p, btnUpdate);
                        };

                        // 次要操作：⋯ 菜单
                        const btnMore = document.createElement("button");
                        btnMore.className = "em-btn em-plugin-btn";
                        btnMore.textContent = "⋯";
                        btnMore.title = "更多操作";
                        btnMore.style.padding = "0 9px";
                        btnMore.onclick = (e) => {
                            e.stopPropagation();
                            const rect = btnMore.getBoundingClientRect();
                            showContextMenu({
                                clientX: rect.left,
                                clientY: rect.bottom + 2,
                                preventDefault: () => {}
                            }, [
                                { label: "切换版本", action: () => openVersionModal(p.name, () => loadPlugins(false)) },
                                { label: "修复",     action: () => repairPlugin(p, false) },
                                { label: "重装",     action: () => repairPlugin(p, true) },
                                { divider: true },
                                { label: "卸载", danger: true, action: () => uninstallPlugin(p) },
                            ]);
                        };

                        actions.appendChild(btnUpdate);
                        actions.appendChild(btnMore);
                    } else {
                        // 非 git 插件只能卸载
                        const btnUninstall = document.createElement("button");
                        btnUninstall.className = "em-btn em-plugin-btn em-btn-danger";
                        btnUninstall.textContent = "卸载";
                        btnUninstall.onclick = (e) => { e.stopPropagation(); uninstallPlugin(p); };
                        actions.appendChild(btnUninstall);
                    }

                    tbody.appendChild(tr);
                }
            }

            async function loadPlugins(checkUpdate) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px;color:#666;">${checkUpdate ? "正在检查更新，请稍候…" : "加载中…"}</td></tr>`;
                [btnRefresh, btnCheck, btnUpdateAll].forEach(b => b.disabled = true);
                try {
                    const res = await fetch(`/extension_manager/plugins/list?check_update=${checkUpdate ? "1" : "0"}`);
                    const plugins = await res.json();
                    _lastPluginList = plugins;
                    renderTable(plugins);
                } catch (e) {
                    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:#f66;">加载失败: ${_escapeHtml(String(e))}</td></tr>`;
                } finally {
                    [btnRefresh, btnCheck, btnUpdateAll].forEach(b => b.disabled = false);
                }
            }

            // —— 一键更新 ——
            async function updateAll() {
                const ok = await showConfirm({
                    title: "确认更新所有插件?",
                    message: "将对所有 git 插件执行 git pull --ff-only。",
                });
                if (!ok) return;
                btnUpdateAll.disabled = true;
                const oldText = btnUpdateAll.textContent;
                btnUpdateAll.textContent = "更新中…";
                const inProgress = showToast({ type: "info", msg: "正在批量更新...", duration: 0 });
                try {
                    const res  = await fetch("/extension_manager/plugins/update_all", { method: "POST" });
                    const json = await res.json();
                    const results = json.results || [];
                    let updated = 0, errors = 0;
                    const errorLines = [];
                    for (const r of results) {
                        if (r.status === "success") {
                            const noChange = !r.output || _NO_CHANGE_RE.test(r.output);
                            if (!noChange) {
                                markPendingRestart(r.name.replace(/\.disabled$/, ""));
                                updated++;
                            }
                        } else {
                            errors++;
                            errorLines.push(`• ${r.name}: ${r.output}`);
                        }
                    }
                    inProgress.dismiss();
                    const noChangeCount = results.length - updated - errors;
                    const summary = `${updated} 已更新 / ${noChangeCount} 已最新 / ${errors} 失败`;
                    showToast({
                        type: errors > 0 ? "warning" : "success",
                        msg: `批量更新完成: ${summary}`,
                        duration: 6000,
                    });
                    if (errors > 0) {
                        await showCustomDialog({
                            title: "更新失败项",
                            contentHTML: `<div style="font-family:monospace;font-size:11px;color:#ccc;white-space:pre-wrap;max-height:300px;overflow:auto;">${_escapeHtml(errorLines.join("\n"))}</div>`,
                            buttons: [{ label: "知道了", value: true, primary: true }]
                        });
                    }
                    loadPlugins(false);
                } catch (e) {
                    inProgress.dismiss();
                    showToast({ type: "error", msg: "请求失败: " + e });
                } finally {
                    btnUpdateAll.disabled = false;
                    btnUpdateAll.textContent = oldText;
                }
            }

            // —— 安装弹框 ——
            async function openInstallDialog() {
                const url = await showCustomDialog({
                    title: "安装插件",
                    contentHTML: `
                        <div style="margin-bottom:8px;color:#ccc;">输入 Git URL（支持 https / ssh）：</div>
                        <input type="text" id="em-install-url"
                               placeholder="git@github.com:user/repo.git 或 https://..."/>
                        <div style="margin-top:8px;font-size:11px;color:#777;">私有库需要先在容器内配置 SSH key。</div>
                    `,
                    buttons: [
                        { label: "取消", value: null },
                        { label: "安装", value: (content) => content.querySelector("#em-install-url").value.trim(), primary: true },
                    ],
                    onMount: (content, dialog) => {
                        const input  = content.querySelector("#em-install-url");
                        const okBtn  = dialog.querySelector(".em-btn-primary");
                        input.addEventListener("keydown", (e) => {
                            if (e.key === "Enter") { e.preventDefault(); okBtn.click(); }
                        });
                    },
                });
                if (!url) return;

                btnInstallBtn.disabled = true;
                const oldText = btnInstallBtn.textContent;
                btnInstallBtn.textContent = "安装中…";
                const inProgress = showToast({ type: "info", msg: "正在安装...", duration: 0 });
                try {
                    const res  = await fetch("/extension_manager/plugins/install", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({url})
                    });
                    const json = await res.json();
                    inProgress.dismiss();
                    if (json.status === "success") {
                        markPendingRestart(json.name);
                        showToast({ type: "success", msg: `${json.name} 已安装` });
                        loadPlugins(false);
                    } else {
                        showToast({ type: "error", msg: `安装失败: ${json.msg}` });
                    }
                } catch (e) {
                    inProgress.dismiss();
                    showToast({ type: "error", msg: "请求失败: " + e });
                } finally {
                    btnInstallBtn.disabled = false;
                    btnInstallBtn.textContent = oldText;
                }
            }

            // —— 导出/导入清单 ——
            function exportManifest() {
                if (!_lastPluginList || _lastPluginList.length === 0) {
                    showToast({ type: "warning", msg: "请先加载插件列表" });
                    return;
                }
                const items = _lastPluginList
                    .filter(p => p.is_git && p.remote)
                    .map(p => ({
                        name:    p.display_name || p.name,
                        remote:  p.remote,
                        branch:  p.branch || "main",
                        commit:  p.commit || "",
                        enabled: !!p.enabled,
                    }));
                if (items.length === 0) {
                    showToast({ type: "warning", msg: "当前没有可导出的 git 插件" });
                    return;
                }
                const manifest = {
                    exported_at: new Date().toISOString().slice(0, 19).replace("T", " "),
                    source: "ComfyUI-Plugins",
                    plugins: items,
                };
                const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: "application/json" });
                const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = `comfyui-plugins-${ts}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(a.href);
                showToast({ type: "success", msg: `已导出 ${items.length} 个插件清单` });
            }

            async function importManifest() {
                const input = document.createElement("input");
                input.type = "file";
                input.accept = "application/json,.json";
                input.onchange = async () => {
                    const file = input.files && input.files[0];
                    if (!file) return;
                    let manifest;
                    try {
                        const text = await file.text();
                        manifest = JSON.parse(text);
                    } catch (e) {
                        showToast({ type: "error", msg: "清单解析失败: " + e });
                        return;
                    }
                    if (!manifest || !Array.isArray(manifest.plugins) || manifest.plugins.length === 0) {
                        showToast({ type: "error", msg: "清单为空或格式错误" });
                        return;
                    }
                    const choice = await showCustomDialog({
                        title: "确认导入清单",
                        contentHTML: `
                            <div style="line-height:1.6;margin-bottom:14px;">将根据清单批量安装 <b style="color:#ddd;">${manifest.plugins.length}</b> 个插件。<br>已存在的插件会被跳过（不覆盖、不更新）。</div>
                            <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#ccc;cursor:pointer;user-select:none;">
                                <input type="checkbox" id="em-import-pin" style="cursor:pointer;margin:0;">
                                锁定到清单记录的版本（commit）
                            </label>
                        `,
                        buttons: [
                            { label: "取消", value: null },
                            { label: "开始安装", value: (content) => ({ pin: content.querySelector("#em-import-pin").checked }), primary: true },
                        ]
                    });
                    if (!choice) return;

                    btnImport.disabled = true;
                    const oldText = btnImport.textContent;
                    btnImport.textContent = "安装中…";
                    const inProgress = showToast({
                        type: "info",
                        msg: `正在批量安装 ${manifest.plugins.length} 个插件...`,
                        duration: 0,
                    });
                    try {
                        const res = await fetch("/extension_manager/plugins/install_batch", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ plugins: manifest.plugins, pin: choice.pin }),
                        });
                        const json = await res.json();
                        inProgress.dismiss();
                        if (json.status !== "success") {
                            showToast({ type: "error", msg: "导入失败: " + (json.msg || "未知错误") });
                            return;
                        }
                        const results = json.results || [];
                        const counts = { installed: 0, skipped_existing: 0, skipped_conflict: 0, error: 0 };
                        for (const r of results) {
                            counts[r.status] = (counts[r.status] || 0) + 1;
                            if (r.status === "installed") markPendingRestart(r.name);
                        }
                        const summary = `已装 ${counts.installed} / 跳过 ${counts.skipped_existing} / 冲突 ${counts.skipped_conflict} / 失败 ${counts.error}`;
                        const toastType = counts.error > 0 ? "warning" : (counts.installed > 0 ? "success" : "info");
                        showToast({ type: toastType, msg: `导入完成: ${summary}`, duration: 8000 });
                        if (counts.error > 0 || counts.skipped_conflict > 0) {
                            const detailLines = results
                                .filter(r => r.status === "error" || r.status === "skipped_conflict")
                                .map(r => `• ${r.name}: ${r.msg || r.status}`);
                            await showCustomDialog({
                                title: "导入详情（异常项）",
                                contentHTML: `<div style="font-family:monospace;font-size:11px;color:#ccc;white-space:pre-wrap;max-height:300px;overflow:auto;">${_escapeHtml(detailLines.join("\n"))}</div>`,
                                buttons: [{ label: "知道了", value: true, primary: true }]
                            });
                        }
                        loadPlugins(false);
                    } catch (e) {
                        inProgress.dismiss();
                        showToast({ type: "error", msg: "请求失败: " + e });
                    } finally {
                        btnImport.disabled = false;
                        btnImport.textContent = oldText;
                    }
                };
                input.click();
            }

            // —— wiring ——
            btnRefresh.onclick    = () => loadPlugins(false);
            btnCheck.onclick      = () => loadPlugins(true);
            btnUpdateAll.onclick  = updateAll;
            btnInstallBtn.onclick = openInstallDialog;
            btnExport.onclick     = exportManifest;
            btnImport.onclick     = importManifest;
            btnReboot.onclick     = rebootComfyUI;

            // 搜索（实时过滤，KISS：列表通常 <100 项，不需要去抖）
            searchInput.oninput = () => {
                _searchTerm = searchInput.value.trim().toLowerCase();
                renderTable(_lastPluginList);
            };

            loadPlugins(false);
        }

        // ================= 主弹窗（命令触发）=================
        let _mainModalEl = null;
        function openModal() {
            const MODAL_ID = "em-plugins-modal";
            if (!_mainModalEl) {
                const overlay = document.createElement("div");
                overlay.id = MODAL_ID;
                overlay.style.cssText = [
                    "position:fixed;inset:0;z-index:9998;",
                    "background:rgba(0,0,0,0.65);",
                    "display:none;align-items:center;justify-content:center;"
                ].join("");

                const dialog = document.createElement("div");
                dialog.style.cssText = [
                    "width:88vw;max-width:1280px;height:82vh;",
                    "background:var(--comfy-menu-bg,#1e1e1e);",
                    "border-radius:8px;border:1px solid #333;",
                    "display:flex;flex-direction:column;overflow:hidden;",
                    "box-shadow:0 8px 40px rgba(0,0,0,0.6);"
                ].join("");

                const titleBar = document.createElement("div");
                titleBar.style.cssText = [
                    "flex-shrink:0;padding:10px 16px;",
                    "border-bottom:1px solid #2a2a2a;background:#1a1a1a;",
                    "display:flex;align-items:center;justify-content:space-between;"
                ].join("");
                titleBar.innerHTML = `
                    <span style="font-size:13px;font-weight:600;color:#ddd;letter-spacing:0.03em;">扩展管理</span>
                    <button id="em-plugins-modal-close" style="
                        background:none;border:none;color:#666;cursor:pointer;
                        font-size:18px;line-height:1;padding:2px 8px;border-radius:3px;
                        font-family:inherit;transition:color 0.15s;
                    ">✕</button>
                `;

                const content = document.createElement("div");
                content.style.cssText = "flex:1;display:flex;flex-direction:column;overflow:hidden;";

                dialog.appendChild(titleBar);
                dialog.appendChild(content);
                overlay.appendChild(dialog);
                document.body.appendChild(overlay);

                const closeModal = () => { overlay.style.display = "none"; };
                const closeBtn = titleBar.querySelector("#em-plugins-modal-close");
                closeBtn.onmouseover = () => { closeBtn.style.color = "#ccc"; };
                closeBtn.onmouseout  = () => { closeBtn.style.color = "#666"; };
                closeBtn.onclick = closeModal;
                overlay.addEventListener("click", (e) => { if (e.target === overlay) closeModal(); });
                document.addEventListener("keydown", (e) => {
                    if (e.key === "Escape" && overlay.style.display === "flex") closeModal();
                });

                createPluginsPanel(content);
                _mainModalEl = overlay;
            }
            _mainModalEl.style.display = "flex";
        }

        // 暴露给命令系统调用
        _openExtensionManagerModal = openModal;
    }
});
