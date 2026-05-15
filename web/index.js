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
                .em-plugin-badge {
                    display: inline-block; padding: 1px 6px; border-radius: 3px;
                    font-size: 11px; font-weight: 500;
                }
                .em-badge-green  { background: #1a3a1a; color: #6c6; border: 1px solid #2a5a2a; }
                .em-badge-yellow { background: #3a2e00; color: #cc6; border: 1px solid #5a4800; }
                .em-badge-gray   { background: #2a2a2a; color: #777; border: 1px solid #3a3a3a; }

                .em-header {
                    flex-shrink: 0; padding: 8px; border-bottom: 1px solid #2a2a2a;
                    display: flex; flex-direction: column; gap: 6px;
                }
                .em-toolbar { display: flex; gap: 4px; align-items: center; }
            `;
            document.head.appendChild(style);
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
                        <td class="em-plugin-commit">${c.short}</td>
                        <td style="max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#ccc;"
                            title="${c.message.replace(/"/g, "&quot;")}">${c.message}</td>
                        <td style="color:#888;font-size:11px;white-space:nowrap;">${c.date}</td>
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
                                    alert(`已切换到 ${c.short}，重启 ComfyUI 后生效`);
                                    if (onSwitch) onSwitch();
                                } else {
                                    alert(`切换失败: ${j.msg}`);
                                    btn.disabled = false; btn.textContent = "切换";
                                }
                            } catch (e) {
                                alert("请求失败: " + e);
                                btn.disabled = false; btn.textContent = "切换";
                            }
                        };
                        tr.querySelector("td:last-child").appendChild(btn);
                    }
                    tbody.appendChild(tr);
                }
            } catch (e) {
                tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#f66;">加载失败: ${e}</td></tr>`;
            }
        }

        // ================= 插件管理面板 =================
        function createPluginsPanel(container) {
            container.innerHTML = `
                <div class="em-header">
                    <div class="em-toolbar">
                        <button class="em-btn" id="em-plugin-refresh">刷新列表</button>
                        <button class="em-btn" id="em-plugin-check">检查更新</button>
                        <button class="em-btn" id="em-plugin-update-all">一键更新</button>
                    </div>
                    <div style="font-size:11px;color:#777;padding:2px 2px 0;">
                        提示：启用/禁用、安装、卸载、切换版本后均需重启 ComfyUI 才能生效
                    </div>
                </div>
                <div class="em-plugin-thead-wrap">
                    <table class="em-plugin-table" id="em-plugin-thead-table">
                        <colgroup>
                            <col style="width:40px;">
                            <col style="width:220px;">
                            <col style="width:320px;">
                            <col style="width:80px;">
                            <col style="width:80px;">
                            <col style="width:140px;">
                            <col style="width:90px;">
                            <col style="width:360px;">
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
                            <col style="width:220px;">
                            <col style="width:320px;">
                            <col style="width:80px;">
                            <col style="width:80px;">
                            <col style="width:140px;">
                            <col style="width:90px;">
                            <col style="width:360px;">
                        </colgroup>
                        <tbody id="em-plugin-tbody"></tbody>
                    </table>
                </div>
                <div style="flex-shrink:0;padding:8px 10px;border-top:1px solid #2a2a2a;display:flex;gap:6px;align-items:center;">
                    <input id="em-plugin-url" type="text" placeholder="粘贴 Git URL 安装插件…"
                        style="flex:1;height:30px;padding:0 10px;background:#1e1e1e;border:1px solid #3a3a3a;
                               border-radius:5px;color:#ccc;font-size:12px;font-family:inherit;box-sizing:border-box;outline:none;"/>
                    <button class="em-btn" id="em-plugin-install" style="flex:none;padding:0 18px;height:30px;">安装</button>
                </div>
            `;

            const tbody        = container.querySelector("#em-plugin-tbody");
            const btnRefresh   = container.querySelector("#em-plugin-refresh");
            const btnCheck     = container.querySelector("#em-plugin-check");
            const btnUpdateAll = container.querySelector("#em-plugin-update-all");
            const headerWrap   = container.querySelector(".em-plugin-thead-wrap");
            const scrollWrap   = container.querySelector(".em-plugin-scroll");

            _setupResizableTable(headerWrap, scrollWrap, "em_plugin_col_widths");

            function statusBadge(p) {
                if (!p.is_git)              return `<span class="em-plugin-badge em-badge-gray">非git</span>`;
                if (p.has_update)           return `<span class="em-plugin-badge em-badge-yellow">有更新</span>`;
                if (p.has_update === false) return `<span class="em-plugin-badge em-badge-green">最新</span>`;
                return `<span class="em-plugin-badge em-badge-gray">未检查</span>`;
            }

            async function repairPlugin(p, clean, btn) {
                const title = clean ? "重装" : "修复";
                const message = clean
                    ? `确认重装 "${p.name}"？\n\n这会恢复远端版本，并删除本地额外文件（包括 .gitignore 忽略的文件）。`
                    : `确认修复 "${p.name}"？\n\n这会恢复缺失或被修改的仓库文件，但保留本地额外文件。`;
                if (!confirm(message)) return;

                const oldText = btn.textContent;
                btn.disabled = true;
                btn.textContent = title + "中";
                try {
                    const res = await fetch("/extension_manager/plugins/repair", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({name: p.name, clean})
                    });
                    const json = await res.json();
                    if (json.status === "success") {
                        alert(`${p.name} ${title}完成:\n${json.output || "完成"}`);
                        loadPlugins(false);
                    } else {
                        alert(`${title}失败: ${json.msg}`);
                        btn.disabled = false;
                        btn.textContent = oldText;
                    }
                } catch (e) {
                    alert("请求失败: " + e);
                    btn.disabled = false;
                    btn.textContent = oldText;
                }
            }

            function renderTable(plugins) {
                tbody.innerHTML = "";
                for (const p of plugins) {
                    const tr = document.createElement("tr");
                    if (!p.enabled) tr.style.opacity = "0.5";
                    const displayName = p.display_name || p.name;
                    tr.innerHTML = `
                        <td style="text-align:center;"></td>
                        <td class="em-plugin-name" title="${p.name}">${displayName}</td>
                        <td class="em-plugin-remote" title="${p.remote || ""}">${p.remote || "-"}</td>
                        <td>${p.branch || "-"}</td>
                        <td class="em-plugin-commit">${p.commit || "-"}</td>
                        <td>${p.date ? p.date.slice(0, 16) : "-"}</td>
                        <td>${statusBadge(p)}</td>
                        <td class="em-plugin-actions"></td>
                    `;

                    const chk = document.createElement("input");
                    chk.type = "checkbox";
                    chk.checked = !!p.enabled;
                    chk.title = p.enabled ? "点击禁用（重启生效）" : "点击启用（重启生效）";
                    chk.style.cursor = "pointer";
                    chk.onchange = async () => {
                        chk.disabled = true;
                        try {
                            const res  = await fetch("/extension_manager/plugins/toggle", {
                                method: "POST",
                                headers: {"Content-Type": "application/json"},
                                body: JSON.stringify({name: p.name})
                            });
                            const json = await res.json();
                            if (json.status === "success") {
                                loadPlugins(false);
                            } else {
                                alert(`操作失败: ${json.msg}`);
                                chk.checked = !chk.checked;
                                chk.disabled = false;
                            }
                        } catch (e) {
                            alert("请求失败: " + e);
                            chk.checked = !chk.checked;
                            chk.disabled = false;
                        }
                    };
                    tr.querySelector("td:first-child").appendChild(chk);

                    const actions = tr.querySelector(".em-plugin-actions");

                    if (p.is_git) {
                        const btnUpdate = document.createElement("button");
                        btnUpdate.className = "em-btn em-plugin-btn";
                        btnUpdate.textContent = "更新";
                        btnUpdate.onclick = async () => {
                            btnUpdate.disabled = true;
                            btnUpdate.textContent = "更新中…";
                            try {
                                const res  = await fetch("/extension_manager/plugins/update", {
                                    method: "POST",
                                    headers: {"Content-Type": "application/json"},
                                    body: JSON.stringify({name: p.name})
                                });
                                const json = await res.json();
                                if (json.status === "success") {
                                    alert(`${p.name} 更新成功:\n${json.output || "Already up to date."}`);
                                    loadPlugins(false);
                                } else {
                                    alert(`更新失败: ${json.msg}`);
                                    btnUpdate.disabled = false;
                                    btnUpdate.textContent = "更新";
                                }
                            } catch (e) {
                                alert("请求失败: " + e);
                                btnUpdate.disabled = false;
                                btnUpdate.textContent = "更新";
                            }
                        };

                        const btnVersion = document.createElement("button");
                        btnVersion.className = "em-btn em-plugin-btn";
                        btnVersion.textContent = "切换版本";
                        btnVersion.onclick = () => openVersionModal(p.name, () => loadPlugins(false));

                        const btnRepair = document.createElement("button");
                        btnRepair.className = "em-btn em-plugin-btn";
                        btnRepair.textContent = "修复";
                        btnRepair.title = "恢复缺失或被修改的仓库文件，保留本地额外文件";
                        btnRepair.onclick = () => repairPlugin(p, false, btnRepair);

                        const btnReinstall = document.createElement("button");
                        btnReinstall.className = "em-btn em-plugin-btn em-btn-danger";
                        btnReinstall.textContent = "重装";
                        btnReinstall.title = "恢复远端版本，并清理本地额外文件";
                        btnReinstall.onclick = () => repairPlugin(p, true, btnReinstall);

                        actions.appendChild(btnUpdate);
                        actions.appendChild(btnVersion);
                        actions.appendChild(btnRepair);
                        actions.appendChild(btnReinstall);
                    }

                    const btnUninstall = document.createElement("button");
                    btnUninstall.className = "em-btn em-plugin-btn em-btn-danger";
                    btnUninstall.textContent = "卸载";
                    btnUninstall.onclick = async () => {
                        if (!confirm(`确认卸载 "${p.name}"？\n此操作不可恢复，重启后生效！`)) return;
                        try {
                            const res  = await fetch("/extension_manager/plugins/uninstall", {
                                method: "POST",
                                headers: {"Content-Type": "application/json"},
                                body: JSON.stringify({name: p.name})
                            });
                            const json = await res.json();
                            if (json.status === "success") {
                                alert(`${p.name} 已卸载，重启 ComfyUI 后生效`);
                                loadPlugins(false);
                            } else {
                                alert(`卸载失败: ${json.msg}`);
                            }
                        } catch (e) {
                            alert("请求失败: " + e);
                        }
                    };
                    actions.appendChild(btnUninstall);

                    tbody.appendChild(tr);
                }
            }

            async function loadPlugins(checkUpdate) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px;color:#666;">${checkUpdate ? "正在检查更新，请稍候…" : "加载中…"}</td></tr>`;
                [btnRefresh, btnCheck, btnUpdateAll].forEach(b => b.disabled = true);
                try {
                    const res = await fetch(`/extension_manager/plugins/list?check_update=${checkUpdate ? "1" : "0"}`);
                    const plugins = await res.json();
                    renderTable(plugins);
                } catch (e) {
                    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:#f66;">加载失败: ${e}</td></tr>`;
                } finally {
                    [btnRefresh, btnCheck, btnUpdateAll].forEach(b => b.disabled = false);
                }
            }

            const urlInput   = container.querySelector("#em-plugin-url");
            const btnInstall = container.querySelector("#em-plugin-install");

            btnRefresh.onclick   = () => loadPlugins(false);
            btnCheck.onclick     = () => loadPlugins(true);
            btnUpdateAll.onclick = async () => {
                if (!confirm("确认更新所有插件？")) return;
                btnUpdateAll.disabled = true;
                btnUpdateAll.textContent = "更新中…";
                try {
                    const res  = await fetch("/extension_manager/plugins/update_all", {method: "POST"});
                    const json = await res.json();
                    const summary = json.results
                        .map(r => `${r.name}: ${r.status === "success" ? "✓ " + (r.output || "已是最新") : "✗ " + r.output}`)
                        .join("\n");
                    alert("更新完成:\n\n" + summary);
                    loadPlugins(false);
                } catch (e) {
                    alert("请求失败: " + e);
                } finally {
                    btnUpdateAll.disabled = false;
                    btnUpdateAll.textContent = "一键更新";
                }
            };

            btnInstall.onclick = async () => {
                const url = urlInput.value.trim();
                if (!url) { urlInput.focus(); return; }
                btnInstall.disabled = true;
                btnInstall.textContent = "安装中…";
                try {
                    const res  = await fetch("/extension_manager/plugins/install", {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({url})
                    });
                    const json = await res.json();
                    if (json.status === "success") {
                        urlInput.value = "";
                        alert(`${json.name} 安装成功，重启 ComfyUI 后生效`);
                        loadPlugins(false);
                    } else {
                        alert(`安装失败: ${json.msg}`);
                    }
                } catch (e) {
                    alert("请求失败: " + e);
                } finally {
                    btnInstall.disabled = false;
                    btnInstall.textContent = "安装";
                }
            };
            urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") btnInstall.click(); });

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
