import os
import re
import sys
import json
import time
import shutil
import subprocess
import asyncio
import urllib.request
import urllib.error
from aiohttp import web
from server import PromptServer

routes = PromptServer.instance.routes

# ================ GitHub 元数据缓存 ================

_GITHUB_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".github_cache.json")
_GITHUB_CACHE_TTL  = 86400  # 24h（成功 / 持久错误）
_GITHUB_RATELIMIT_TTL = 3600  # 1h（限流：GitHub 限额按小时重置）
_github_cache = None        # 模块级内存缓存：{ "owner/repo": {stars, author, fetched_at} }


def _cache_valid(entry, now):
    """根据条目类型选择 TTL：限流走 1h，其余走 24h。"""
    if not entry:
        return False
    age = now - entry.get("fetched_at", 0)
    ttl = _GITHUB_RATELIMIT_TTL if entry.get("error") == "rate_limited" else _GITHUB_CACHE_TTL
    return age < ttl


def _parse_github(remote):
    """解析 GitHub remote → (owner, repo)；支持 https / ssh，均不区分 .git 后缀。失败返回 (None, None)。"""
    if not remote:
        return None, None
    s = remote.strip()
    # git@github.com:owner/repo(.git)
    m = re.match(r"^git@github\.com:([^/]+)/(.+?)(?:\.git)?/?$", s, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    # https://github.com/owner/repo(.git)
    m = re.match(r"^https?://github\.com/([^/]+)/(.+?)(?:\.git)?/?$", s, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    return None, None


def _load_github_cache():
    global _github_cache
    if _github_cache is not None:
        return _github_cache
    try:
        with open(_GITHUB_CACHE_FILE, "r", encoding="utf-8") as f:
            _github_cache = json.load(f)
        if not isinstance(_github_cache, dict):
            _github_cache = {}
    except Exception:
        _github_cache = {}
    return _github_cache


def _save_github_cache():
    try:
        with open(_GITHUB_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_github_cache, f)
    except Exception:
        pass  # 只读环境等：静默忽略


def _fetch_github_repo(owner, repo):
    """请求 GitHub API，返回 (stars, author) 或抛异常（含 HTTPError，便于识别限流）。"""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Koh-ExtensionManager")
    req.add_header("Accept", "application/vnd.github+json")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    stars  = data.get("stargazers_count")
    author = (data.get("owner") or {}).get("login") or owner
    return stars, author


# ---- 复用 ComfyUI-Manager 预聚合的星标快照（避免 GitHub 限流）----
# ComfyUI-Manager 维护两个 JSON：github-stats.json（上游快照，~5000 项）+ github-stats-cache.json（增量）
_external_stats       = None   # 合并后的 dict：{ "https://github.com/owner/repo": {stars,...} }
_external_stats_mtime = None   # (mtime1, mtime2) 元组，文件变化时重载


def _comfyui_manager_dir():
    """定位同级 ComfyUI-Manager 目录（含 .disabled 变体），不存在则返回 None。"""
    nodes_dir = _get_custom_nodes_dir()
    for cand in ("ComfyUI-Manager", "ComfyUI-Manager.disabled"):
        p = os.path.join(nodes_dir, cand)
        if os.path.isdir(p):
            return p
    return None


def _load_external_stats():
    """惰性加载 + mtime 失效检测。两个文件均不存在返回空 dict。"""
    global _external_stats, _external_stats_mtime
    mgr = _comfyui_manager_dir()
    if not mgr:
        _external_stats = {}
        _external_stats_mtime = None
        return _external_stats

    files = [
        os.path.join(mgr, "github-stats.json"),
        os.path.join(mgr, "github-stats-cache.json"),
    ]
    mtimes = tuple(os.path.getmtime(f) if os.path.isfile(f) else 0 for f in files)
    if _external_stats is not None and mtimes == _external_stats_mtime:
        return _external_stats

    merged = {}
    for f in files:
        if not os.path.isfile(f):
            continue
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            if isinstance(d, dict):
                merged.update(d)  # github-stats-cache.json 后加载，覆盖前者
        except Exception:
            pass
    _external_stats = merged
    _external_stats_mtime = mtimes
    return _external_stats


def _lookup_external(owner, repo):
    """从外部快照查 stars/author。命中返回 {stars, author}，否则 None。"""
    if not owner or not repo:
        return None
    stats = _load_external_stats()
    key = f"https://github.com/{owner}/{repo}"
    entry = stats.get(key)
    if entry is None:
        # 有的 key 是错别字 'htps://'，尝试一次
        entry = stats.get("htps://github.com/" + owner + "/" + repo)
    if entry is None:
        return None
    stars = entry.get("stars")
    if stars is None:
        return None
    return {"stars": stars, "author": owner}


# ================ 辅助函数 ================

def _get_custom_nodes_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _run_git(cwd, *args, timeout=30):
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)

def _get_plugin_info(plugin_dir, check_update=False):
    name = os.path.basename(plugin_dir)
    enabled = not name.endswith(".disabled")
    display_name = name[:-9] if not enabled else name  # 去掉 ".disabled" 后缀

    if not os.path.isdir(os.path.join(plugin_dir, ".git")):
        return {"name": name, "display_name": display_name, "is_git": False, "enabled": enabled}

    code, remote, _ = _run_git(plugin_dir, "remote", "get-url", "origin")
    remote = remote if code == 0 else ""

    code, branch, _ = _run_git(plugin_dir, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch if code == 0 else "unknown"

    code, commit, _ = _run_git(plugin_dir, "rev-parse", "--short", "HEAD")
    commit = commit if code == 0 else ""

    code, date_str, _ = _run_git(plugin_dir, "log", "-1", "--format=%ci")
    date_str = date_str[:19] if (code == 0 and date_str) else ""

    has_update = None
    if check_update and remote:
        c, _, _ = _run_git(plugin_dir, "fetch", "origin", timeout=20)
        if c == 0:
            c2, local_head, _ = _run_git(plugin_dir, "rev-parse", "HEAD")
            c3, remote_head, _ = _run_git(plugin_dir, "rev-parse", f"origin/{branch}")
            if c2 == 0 and c3 == 0:
                has_update = local_head != remote_head

    return {
        "name": name,
        "display_name": display_name,
        "is_git": True,
        "enabled": enabled,
        "remote": remote,
        "branch": branch,
        "commit": commit,
        "date": date_str,
        "has_update": has_update,
    }


# ================ 安装后处理：依赖 / install.py ================

def _comfyui_root():
    """ComfyUI 根目录 = custom_nodes 的上一级。"""
    return os.path.dirname(_get_custom_nodes_dir())


def _get_comfyui_version():
    """读 ComfyUI 主目录 git 信息：branch / commit / tag。

    失败返回 None（非 git 仓库 / 命令异常）。tag 用 git describe --tags --exact-match
    取"恰好在此 commit 上的 tag"，没有则为空字符串（表示当前是 master/nightly 状态）。
    """
    root = _comfyui_root()
    if not os.path.isdir(os.path.join(root, ".git")):
        return None
    c1, branch, _ = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    c2, commit, _ = _run_git(root, "rev-parse", "HEAD")
    if c1 != 0 or c2 != 0:
        return None
    c3, tag, _ = _run_git(root, "describe", "--tags", "--exact-match", "HEAD")
    return {
        "branch": branch,
        "commit": commit,
        "tag": tag if c3 == 0 else "",
    }


def _tail(s, n=2000):
    """截取尾部 n 字符（pip 报错关键信息通常在末尾）。"""
    s = (s or "").strip()
    return s[-n:] if len(s) > n else s


def _post_install_setup(plugin_dir, timeout=600):
    """clone 之后处理依赖。返回 (ok: bool, log: str)。

    优先调 ComfyUI-Manager 的 cm-cli.py post-install：复用其 pip 安装 +
    install.py + PIPFixer（torch 回滚 / opencv 去重等）全套逻辑，且该子命令
    不联网拉注册表，适配无外网环境。
    Manager 不在时 fallback 到内置实现（pip install -r requirements.txt + install.py）。
    """
    mgr   = _comfyui_manager_dir()
    cmcli = os.path.join(mgr, "cm-cli.py") if mgr else None

    if cmcli and os.path.isfile(cmcli):
        env = dict(os.environ)
        env["COMFYUI_PATH"] = _comfyui_root()  # 显式指定，避免子进程靠猜
        try:
            r = subprocess.run(
                [sys.executable, cmcli, "post-install", plugin_dir],
                cwd=mgr, capture_output=True, text=True, timeout=timeout, env=env
            )
            log = f"[cm-cli post-install] rc={r.returncode}\n{_tail(r.stdout)}\n{_tail(r.stderr)}"
            return (r.returncode == 0), log.strip()
        except subprocess.TimeoutExpired:
            return False, "cm-cli post-install 超时"
        except Exception as e:
            return False, f"cm-cli post-install 调用失败: {e}"

    return _post_install_fallback(plugin_dir, timeout=timeout)


def _post_install_fallback(plugin_dir, timeout=600):
    """Manager 不可用时的兜底：自己装 requirements.txt + 跑 install.py。"""
    outputs = ["[fallback] ComfyUI-Manager 不可用，使用内置依赖安装"]
    py = sys.executable  # ComfyUI 当前的 Python，避免装错环境

    def _step(label, args):
        try:
            r = subprocess.run(
                args, cwd=plugin_dir, capture_output=True, text=True, timeout=timeout
            )
            outputs.append(f"[{label}] rc={r.returncode}\n{_tail(r.stdout)}\n{_tail(r.stderr)}")
            return r.returncode == 0
        except subprocess.TimeoutExpired:
            outputs.append(f"[{label}] 超时")
            return False
        except Exception as e:
            outputs.append(f"[{label}] 异常: {e}")
            return False

    if os.path.isfile(os.path.join(plugin_dir, "requirements.txt")):
        if not _step("pip", [py, "-m", "pip", "install", "-r", "requirements.txt"]):
            return False, "\n".join(outputs)

    if os.path.isfile(os.path.join(plugin_dir, "install.py")):
        if not _step("install.py", [py, "install.py"]):
            return False, "\n".join(outputs)

    return True, "\n".join(outputs)


# ================ 路由 ================

def _get_git_plugin_dir(name):
    nodes_dir = _get_custom_nodes_dir()
    plugin_dir = os.path.normpath(os.path.join(nodes_dir, name))
    if not plugin_dir.startswith(os.path.normpath(nodes_dir) + os.sep):
        return None, "Invalid path"
    if not os.path.isdir(plugin_dir):
        return None, "Plugin not found"
    if not os.path.isdir(os.path.join(plugin_dir, ".git")):
        return None, "Plugin is not a git repository"
    return plugin_dir, ""


def _reset_plugin_repo(plugin_dir, clean=False):
    code, branch, _ = _run_git(plugin_dir, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch if code == 0 else "HEAD"

    target = "HEAD"
    outputs = []

    if branch != "HEAD":
        code, stdout, stderr = _run_git(plugin_dir, "fetch", "origin", timeout=60)
        if code != 0:
            return code, stdout, stderr
        if stdout:
            outputs.append(stdout)

        code, _, _ = _run_git(plugin_dir, "rev-parse", "--verify", f"origin/{branch}")
        if code != 0:
            return code, "", f"Remote branch origin/{branch} not found"
        target = f"origin/{branch}"

    code, stdout, stderr = _run_git(plugin_dir, "reset", "--hard", target, timeout=60)
    if code != 0:
        return code, stdout, stderr
    if stdout:
        outputs.append(stdout)

    if clean:
        code, stdout, stderr = _run_git(plugin_dir, "clean", "-fdx", timeout=60)
        if code != 0:
            return code, "\n".join(outputs + ([stdout] if stdout else [])), stderr
        if stdout:
            outputs.append(stdout)

    return 0, "\n".join(outputs).strip(), ""


@routes.get("/extension_manager/plugins/list")
async def plugins_list(request):
    check_update = request.rel_url.query.get("check_update", "0") == "1"
    nodes_dir = _get_custom_nodes_dir()
    loop = asyncio.get_event_loop()
    try:
        entries = sorted(
            [e for e in os.scandir(nodes_dir) if e.is_dir() and not e.name.startswith(".")],
            key=lambda x: x.name.lower()
        )
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

    def build_list():
        return [_get_plugin_info(e.path, check_update=check_update) for e in entries]

    plugins = await loop.run_in_executor(None, build_list)
    return web.json_response(plugins)


@routes.post("/extension_manager/plugins/update")
async def plugin_update(request):
    try:
        data = await request.json()
        name = data.get("name", "")
        if not name:
            return web.json_response({"status": "error", "msg": "Missing name"}, status=400)

        nodes_dir = _get_custom_nodes_dir()
        plugin_dir = os.path.normpath(os.path.join(nodes_dir, name))
        if not plugin_dir.startswith(os.path.normpath(nodes_dir) + os.sep):
            return web.json_response({"status": "error", "msg": "Invalid path"}, status=403)
        if not os.path.isdir(plugin_dir):
            return web.json_response({"status": "error", "msg": "Plugin not found"}, status=404)

        loop = asyncio.get_event_loop()
        code, stdout, stderr = await loop.run_in_executor(
            None, lambda: _run_git(plugin_dir, "pull", "--ff-only", timeout=60)
        )
        if code != 0:
            return web.json_response({"status": "error", "msg": stderr or stdout}, status=500)
        return web.json_response({"status": "success", "output": stdout})
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


@routes.post("/extension_manager/plugins/update_all")
async def plugin_update_all(request):
    nodes_dir = _get_custom_nodes_dir()
    try:
        entries = [e for e in os.scandir(nodes_dir) if e.is_dir() and not e.name.startswith(".")]
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)

    loop = asyncio.get_event_loop()

    async def pull_one(plugin_dir):
        if not os.path.isdir(os.path.join(plugin_dir, ".git")):
            return None
        code, stdout, stderr = await loop.run_in_executor(
            None, lambda d=plugin_dir: _run_git(d, "pull", "--ff-only", timeout=60)
        )
        return {
            "name": os.path.basename(plugin_dir),
            "status": "success" if code == 0 else "error",
            "output": stdout if code == 0 else (stderr or stdout)
        }

    tasks = [pull_one(e.path) for e in entries]
    results = [r for r in await asyncio.gather(*tasks) if r is not None]
    return web.json_response({"status": "success", "results": results})


@routes.post("/extension_manager/plugins/repair")
async def plugin_repair(request):
    try:
        data = await request.json()
        name = data.get("name", "")
        clean = bool(data.get("clean", False))
        if not name:
            return web.json_response({"status": "error", "msg": "Missing name"}, status=400)

        plugin_dir, error = _get_git_plugin_dir(name)
        if error:
            status = 403 if error == "Invalid path" else 404
            return web.json_response({"status": "error", "msg": error}, status=status)

        loop = asyncio.get_event_loop()
        code, stdout, stderr = await loop.run_in_executor(
            None, lambda: _reset_plugin_repo(plugin_dir, clean=clean)
        )
        if code != 0:
            return web.json_response({"status": "error", "msg": stderr or stdout}, status=500)
        return web.json_response({"status": "success", "output": stdout})
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


@routes.get("/extension_manager/plugins/commits")
async def plugin_commits(request):
    name = request.rel_url.query.get("name", "")
    if not name:
        return web.json_response({"error": "Missing name"}, status=400)

    nodes_dir = _get_custom_nodes_dir()
    plugin_dir = os.path.normpath(os.path.join(nodes_dir, name))
    if not plugin_dir.startswith(os.path.normpath(nodes_dir) + os.sep):
        return web.json_response({"error": "Invalid path"}, status=403)

    loop = asyncio.get_event_loop()

    def get_commits():
        code, current_hash, _ = _run_git(plugin_dir, "rev-parse", "HEAD")
        current = current_hash if code == 0 else ""

        code, log_out, _ = _run_git(plugin_dir, "log", "--pretty=format:%H|%h|%s|%ci", "-80")
        if code != 0:
            return {"commits": [], "current": current}

        commits = []
        for line in log_out.splitlines():
            if not line.strip():
                continue
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            commits.append({
                "hash":    parts[0],
                "short":   parts[1],
                "message": parts[2],
                "date":    parts[3][:16],
            })
        return {"commits": commits, "current": current}

    result = await loop.run_in_executor(None, get_commits)
    return web.json_response(result)


@routes.post("/extension_manager/plugins/checkout")
async def plugin_checkout(request):
    try:
        data = await request.json()
        name = data.get("name", "")
        ref  = data.get("ref", "")
        if not name or not ref:
            return web.json_response({"status": "error", "msg": "Missing name or ref"}, status=400)

        nodes_dir = _get_custom_nodes_dir()
        plugin_dir = os.path.normpath(os.path.join(nodes_dir, name))
        if not plugin_dir.startswith(os.path.normpath(nodes_dir) + os.sep):
            return web.json_response({"status": "error", "msg": "Invalid path"}, status=403)
        if not os.path.isdir(plugin_dir):
            return web.json_response({"status": "error", "msg": "Plugin not found"}, status=404)

        loop = asyncio.get_event_loop()
        code, stdout, stderr = await loop.run_in_executor(
            None, lambda: _run_git(plugin_dir, "checkout", ref, timeout=30)
        )
        if code != 0:
            return web.json_response({"status": "error", "msg": stderr or stdout}, status=500)
        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


@routes.post("/extension_manager/plugins/toggle")
async def plugin_toggle(request):
    try:
        data = await request.json()
        name = data.get("name", "")
        if not name:
            return web.json_response({"status": "error", "msg": "Missing name"}, status=400)

        nodes_dir  = _get_custom_nodes_dir()
        plugin_dir = os.path.normpath(os.path.join(nodes_dir, name))
        if not plugin_dir.startswith(os.path.normpath(nodes_dir) + os.sep):
            return web.json_response({"status": "error", "msg": "Invalid path"}, status=403)
        if not os.path.isdir(plugin_dir):
            return web.json_response({"status": "error", "msg": "Plugin not found"}, status=404)

        was_disabled = name.endswith(".disabled")
        new_name = name[:-9] if was_disabled else name + ".disabled"
        new_dir  = os.path.join(nodes_dir, new_name)

        if os.path.exists(new_dir):
            return web.json_response({"status": "error", "msg": f"目标路径已存在: {new_name}"}, status=400)

        os.rename(plugin_dir, new_dir)
        return web.json_response({"status": "success", "new_name": new_name, "enabled": was_disabled})
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


@routes.post("/extension_manager/plugins/install")
async def plugin_install(request):
    try:
        data = await request.json()
        url  = data.get("url", "").strip()
        if not url:
            return web.json_response({"status": "error", "msg": "Missing URL"}, status=400)

        # 从 URL 提取目录名（取最后一段，去掉 .git 后缀）
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        if not name:
            return web.json_response({"status": "error", "msg": "无法从 URL 解析插件名"}, status=400)

        nodes_dir  = _get_custom_nodes_dir()
        target_dir = os.path.join(nodes_dir, name)
        if os.path.exists(target_dir):
            return web.json_response({"status": "error", "msg": f"目录已存在: {name}"}, status=400)

        loop = asyncio.get_event_loop()
        code, stdout, stderr = await loop.run_in_executor(
            None, lambda: _run_git(nodes_dir, "clone", "--depth=1", "--recursive", url, name, timeout=120)
        )
        if code != 0:
            return web.json_response({"status": "error", "msg": stderr or stdout}, status=500)

        # clone 成功 → 装依赖 + 跑 install.py
        ok, log = await loop.run_in_executor(None, lambda: _post_install_setup(target_dir))
        if not ok:
            # 依赖装失败：禁用目录，避免下次启动 ComfyUI 因缺包崩溃
            try:
                os.rename(target_dir, target_dir + ".disabled")
            except Exception:
                pass
            return web.json_response({
                "status": "error",
                "name": name,
                "msg": "代码已下载，但依赖安装失败，已自动禁用以防启动崩溃。\n" + _tail(log, 1800),
            }, status=500)

        return web.json_response({"status": "success", "name": name, "output": _tail(log, 1800)})
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


@routes.post("/extension_manager/plugins/uninstall")
async def plugin_uninstall(request):
    try:
        data = await request.json()
        name = data.get("name", "")
        if not name:
            return web.json_response({"status": "error", "msg": "Missing name"}, status=400)

        nodes_dir = _get_custom_nodes_dir()
        plugin_dir = os.path.normpath(os.path.join(nodes_dir, name))
        if not plugin_dir.startswith(os.path.normpath(nodes_dir) + os.sep):
            return web.json_response({"status": "error", "msg": "Invalid path"}, status=403)
        if not os.path.isdir(plugin_dir):
            return web.json_response({"status": "error", "msg": "Plugin not found"}, status=404)

        shutil.rmtree(plugin_dir)
        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


def _normalize_remote(s):
    """规范化 remote URL 用于对比同仓库识别。

    - GitHub URL：提取 owner/repo 比对，吃掉 ssh/https 协议差异、有无 .git 后缀
    - 非 GitHub：去尾斜杠、去 .git 后缀、转小写
    """
    s = (s or "").strip().rstrip("/")
    if not s:
        return ""
    owner, repo = _parse_github(s)
    if owner and repo:
        return f"github.com/{owner.lower()}/{repo.lower()}"
    s = s.lower()
    if s.endswith(".git"):
        s = s[:-4]
    return s


def _install_one_from_manifest(nodes_dir, item, pin):
    """处理单条清单项 → 返回 {name, status, msg} 结果。
    status: installed | skipped_existing | skipped_conflict | error
    """
    name    = (item.get("name") or "").strip()
    remote  = (item.get("remote") or "").strip()
    commit  = (item.get("commit") or "").strip()
    enabled = bool(item.get("enabled", True))

    if not name or not remote:
        return {"name": name or "?", "status": "error", "msg": "Missing name or remote"}

    # 路径安全：禁止分隔符与父级引用
    if any(ch in name for ch in ["/", "\\", ".."]):
        return {"name": name, "status": "error", "msg": "Invalid plugin name"}

    target_dir   = os.path.join(nodes_dir, name)
    disabled_dir = os.path.join(nodes_dir, name + ".disabled")

    # 已存在检测（含 .disabled 变体）
    existing_dir = target_dir if os.path.isdir(target_dir) else (
        disabled_dir if os.path.isdir(disabled_dir) else None
    )
    if existing_dir is not None:
        if not os.path.isdir(os.path.join(existing_dir, ".git")):
            return {"name": name, "status": "skipped_conflict", "msg": "已存在同名目录但非 git 仓库"}
        code, existing_remote, _ = _run_git(existing_dir, "remote", "get-url", "origin")
        if code != 0:
            return {"name": name, "status": "skipped_conflict", "msg": "已存在但无法读取 remote"}
        if _normalize_remote(existing_remote) != _normalize_remote(remote):
            return {"name": name, "status": "skipped_conflict",
                    "msg": f"已存在但 remote 不同: {existing_remote}"}
        return {"name": name, "status": "skipped_existing", "msg": "已存在"}

    # Clone：pin 需要完整历史，否则 shallow 加速
    if pin and commit:
        code, stdout, stderr = _run_git(
            nodes_dir, "clone", "--recursive", remote, name, timeout=180
        )
    else:
        code, stdout, stderr = _run_git(
            nodes_dir, "clone", "--depth=1", "--recursive", remote, name, timeout=120
        )
    if code != 0:
        return {"name": name, "status": "error",
                "msg": (stderr or stdout or "clone failed")[:300]}

    # 可选：锁定到记录 commit
    if pin and commit:
        code, _, stderr = _run_git(target_dir, "checkout", commit, timeout=30)
        if code != 0:
            return {"name": name, "status": "error",
                    "msg": f"clone 成功但 checkout 失败: {stderr[:200]}"}

    # clone（含 checkout）成功 → 装依赖 + 跑 install.py
    ok, log = _post_install_setup(target_dir)
    if not ok:
        # 依赖失败：禁用目录，避免下次启动 ComfyUI 因缺包崩溃
        try:
            if not os.path.isdir(disabled_dir):
                os.rename(target_dir, disabled_dir)
        except Exception:
            pass
        return {"name": name, "status": "error",
                "msg": "代码已下载但依赖安装失败，已禁用。" + _tail(log, 300)}

    # 应用启用/禁用状态
    if not enabled:
        try:
            os.rename(target_dir, disabled_dir)
        except Exception as e:
            return {"name": name, "status": "error", "msg": f"clone 成功但禁用失败: {e}"}
        return {"name": name, "status": "installed", "msg": "已安装（禁用）"}

    return {"name": name, "status": "installed", "msg": "已安装"}


def _update_one_from_manifest(nodes_dir, item, update_mode):
    """更新已安装插件 → {name, status, msg}。
    update_mode: latest（git pull --ff-only）| pin（fetch + checkout 清单 commit）
    status: updated | error
    """
    name   = (item.get("name") or "").strip()
    commit = (item.get("commit") or "").strip()
    if not name:
        return {"name": name or "?", "status": "error", "msg": "Missing name"}
    if any(ch in name for ch in ["/", "\\", ".."]):
        return {"name": name, "status": "error", "msg": "Invalid plugin name"}

    # 定位目录（含 .disabled 变体）
    target_dir   = os.path.join(nodes_dir, name)
    disabled_dir = os.path.join(nodes_dir, name + ".disabled")
    plugin_dir   = target_dir if os.path.isdir(target_dir) else (
        disabled_dir if os.path.isdir(disabled_dir) else None
    )
    if plugin_dir is None:
        return {"name": name, "status": "error", "msg": "插件不存在"}
    if not os.path.isdir(os.path.join(plugin_dir, ".git")):
        return {"name": name, "status": "error", "msg": "非 git 仓库"}

    if update_mode == "pin" and commit:
        code, _, stderr = _run_git(plugin_dir, "fetch", "origin", timeout=60)
        if code != 0:
            return {"name": name, "status": "error", "msg": (stderr or "fetch failed")[:200]}
        code, stdout, stderr = _run_git(plugin_dir, "checkout", commit, timeout=30)
        if code != 0:
            return {"name": name, "status": "error", "msg": (stderr or stdout or "checkout failed")[:200]}
        return {"name": name, "status": "updated", "msg": f"已锁定到 {commit}"}

    code, stdout, stderr = _run_git(plugin_dir, "pull", "--ff-only", timeout=60)
    if code != 0:
        return {"name": name, "status": "error", "msg": (stderr or stdout or "pull failed")[:200]}
    return {"name": name, "status": "updated", "msg": (stdout or "已更新")[:200]}


@routes.post("/extension_manager/plugins/install_batch")
async def plugin_install_batch(request):
    try:
        data        = await request.json()
        plugins     = data.get("plugins", [])
        pin         = bool(data.get("pin", False))
        update_mode = data.get("update_mode", "latest")
        if update_mode not in ("latest", "pin"):
            update_mode = "latest"
        if not isinstance(plugins, list) or not plugins:
            return web.json_response({"status": "error", "msg": "Empty plugins list"}, status=400)

        nodes_dir = _get_custom_nodes_dir()
        loop = asyncio.get_event_loop()

        # 顺序处理：clone/pull 串行更稳，避免 GitHub 限流、便于阅读报告
        results = []
        for item in plugins:
            action = (item.get("action") or "install").strip()
            if action == "update":
                r = await loop.run_in_executor(
                    None, lambda it=item: _update_one_from_manifest(nodes_dir, it, update_mode)
                )
            else:
                r = await loop.run_in_executor(
                    None, lambda it=item: _install_one_from_manifest(nodes_dir, it, pin)
                )
            results.append(r)

        return web.json_response({"status": "success", "results": results})
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


@routes.post("/extension_manager/plugins/uninstall_batch")
async def plugin_uninstall_batch(request):
    """批量卸载（清单导入"对齐到清单"场景使用）。

    入参：{"names": ["pluginA", "pluginB.disabled", ...]}
    返回：{"status": "success", "results": [{name, status: removed|skipped|error, msg}]}
    """
    try:
        data  = await request.json()
        names = data.get("names", [])
        if not isinstance(names, list) or not names:
            return web.json_response({"status": "error", "msg": "Empty names list"}, status=400)

        nodes_dir   = _get_custom_nodes_dir()
        nodes_root  = os.path.normpath(nodes_dir)
        loop        = asyncio.get_event_loop()

        def remove_one(name):
            name = (name or "").strip()
            if not name:
                return {"name": name, "status": "error", "msg": "empty name"}
            # 路径安全：禁止分隔符与父级引用
            if any(ch in name for ch in ["/", "\\", ".."]):
                return {"name": name, "status": "error", "msg": "invalid name"}
            target = os.path.normpath(os.path.join(nodes_dir, name))
            if not target.startswith(nodes_root + os.sep):
                return {"name": name, "status": "error", "msg": "invalid path"}
            if not os.path.isdir(target):
                return {"name": name, "status": "skipped", "msg": "not found"}
            try:
                shutil.rmtree(target)
                return {"name": name, "status": "removed"}
            except Exception as ex:
                return {"name": name, "status": "error", "msg": str(ex)[:200]}

        results = await loop.run_in_executor(
            None, lambda: [remove_one(n) for n in names]
        )
        return web.json_response({"status": "success", "results": results})
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


# ================ GitHub 星标 / 作者 ================

@routes.post("/extension_manager/plugins/github_meta")
async def plugins_github_meta(request):
    """批量查询 GitHub 星标/作者。缓存优先（TTL 24h），过期/缺失才走网络；遇限流停止剩余请求。"""
    try:
        data    = await request.json()
        remotes = data.get("remotes", [])
        if not isinstance(remotes, list):
            return web.json_response({"status": "error", "msg": "remotes must be a list"}, status=400)

        cache = _load_github_cache()
        now   = time.time()
        loop  = asyncio.get_event_loop()

        results      = {}
        rate_limited = False
        dirty        = False

        # 去重（多个 remote 可能指向同一 repo）
        seen = []
        for r in remotes:
            if r and r not in seen:
                seen.append(r)

        for remote in seen:
            owner, repo = _parse_github(remote)
            if not owner or not repo:
                results[remote] = {"stars": None, "author": None, "cached": False}
                continue

            key    = f"{owner}/{repo}"
            cached = cache.get(key)
            if _cache_valid(cached, now):
                results[remote] = {
                    "stars": cached.get("stars"),
                    "author": cached.get("author") or owner,
                    "cached": True, "source": "cache",
                    "rate_limited": cached.get("error") == "rate_limited",
                }
                continue

            # 优先复用 ComfyUI-Manager 的预聚合快照（无网络、无限流）
            ext = _lookup_external(owner, repo)
            if ext is not None:
                results[remote] = {"stars": ext["stars"], "author": ext["author"], "cached": True, "source": "manager"}
                continue

            # 已限流：剩余项回退缓存值（即便过期）或 null
            if rate_limited:
                results[remote] = {
                    "stars": cached.get("stars") if cached else None,
                    "author": cached.get("author") if cached else owner,
                    "cached": bool(cached), "rate_limited": True,
                }
                continue

            try:
                stars, author = await loop.run_in_executor(None, lambda o=owner, p=repo: _fetch_github_repo(o, p))
                cache[key] = {"stars": stars, "author": author, "fetched_at": now}
                dirty = True
                results[remote] = {"stars": stars, "author": author, "cached": False, "source": "network"}
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    # 限流：缓存 1h 避免持续重试（限额按小时重置）
                    rate_limited = True
                    cache[key] = {"stars": None, "author": owner, "fetched_at": now, "error": "rate_limited"}
                    dirty = True
                    results[remote] = {
                        "stars": cached.get("stars") if cached else None,
                        "author": cached.get("author") if cached else owner,
                        "cached": bool(cached), "rate_limited": True,
                    }
                else:
                    # 持久错误（404/私有/重命名等）：缓存为 null 避免每次刷新都重打
                    cache[key] = {"stars": None, "author": owner, "fetched_at": now, "error": f"HTTP {e.code}"}
                    dirty = True
                    results[remote] = {"stars": None, "author": owner, "cached": False, "error": f"HTTP {e.code}", "source": "network"}
            except Exception as e:
                results[remote] = {"stars": None, "author": owner, "cached": False, "error": str(e)[:120]}

        if dirty:
            await loop.run_in_executor(None, _save_github_cache)

        return web.json_response({"status": "success", "results": results, "rate_limited": rate_limited})
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


# ================ 单插件检查更新 ================

@routes.get("/extension_manager/plugins/check_one")
async def plugin_check_one(request):
    name = request.rel_url.query.get("name", "")
    if not name:
        return web.json_response({"status": "error", "msg": "Missing name"}, status=400)

    plugin_dir, error = _get_git_plugin_dir(name)
    if error:
        status = 403 if error == "Invalid path" else 404
        return web.json_response({"status": "error", "msg": error}, status=status)

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, lambda: _get_plugin_info(plugin_dir, check_update=True))
    return web.json_response({"status": "success", "info": info})


# ================ 导入清单：差异对比 ================

@routes.post("/extension_manager/plugins/manifest_diff")
async def plugins_manifest_diff(request):
    """对清单逐项与本地对比 → new | update | same | conflict | extra。

    extra: 本机有但清单未包含的 git 插件（用于"对齐到清单"场景的可选卸载）。
    """
    try:
        data    = await request.json()
        plugins = data.get("plugins", [])
        if not isinstance(plugins, list):
            return web.json_response({"status": "error", "msg": "plugins must be a list"}, status=400)

        nodes_dir = _get_custom_nodes_dir()
        loop      = asyncio.get_event_loop()

        def diff_one(item):
            name   = (item.get("name") or "").strip()
            remote = (item.get("remote") or "").strip()
            m_commit = (item.get("commit") or "").strip()
            m_branch = (item.get("branch") or "").strip()
            owner, _ = _parse_github(remote)

            base = {
                "name": name, "remote": remote,
                "manifest_commit": m_commit, "manifest_branch": m_branch,
                "author": owner, "installed": False,
                "local_commit": "", "local_remote": "",
            }
            if not name or not remote:
                base["status"] = "conflict"
                base["msg"] = "清单项缺少 name 或 remote"
                return base

            target_dir   = os.path.join(nodes_dir, name)
            disabled_dir = os.path.join(nodes_dir, name + ".disabled")
            existing_dir = target_dir if os.path.isdir(target_dir) else (
                disabled_dir if os.path.isdir(disabled_dir) else None
            )

            if existing_dir is None:
                base["status"] = "new"
                return base

            base["installed"] = True
            if not os.path.isdir(os.path.join(existing_dir, ".git")):
                base["status"] = "conflict"
                base["msg"] = "已存在同名目录但非 git 仓库"
                return base

            code, local_remote, _ = _run_git(existing_dir, "remote", "get-url", "origin")
            local_remote = local_remote if code == 0 else ""
            base["local_remote"] = local_remote
            if _normalize_remote(local_remote) != _normalize_remote(remote):
                base["status"] = "conflict"
                base["msg"] = f"已存在但 remote 不同: {local_remote}"
                return base

            code, local_commit, _ = _run_git(existing_dir, "rev-parse", "--short", "HEAD")
            local_commit = local_commit if code == 0 else ""
            base["local_commit"] = local_commit

            # 短哈希前缀互相匹配视为同版本
            same = bool(local_commit) and bool(m_commit) and (
                local_commit.startswith(m_commit) or m_commit.startswith(local_commit)
            )
            base["status"] = "same" if same else "update"
            return base

        def scan_extras(manifest_items):
            """扫本机所有 git 插件，剔除清单已覆盖的（按 name + remote 双重匹配）。

            匹配规则：清单项的 name 与本地目录名一致 OR remote 规范化后一致。
            目的：清单里改过 name 但 remote 不变时不会误报为 extra。
            """
            # 清单里出现过的 name（含 .disabled 兼容）与规范化 remote
            covered_names   = set()
            covered_remotes = set()
            for it in manifest_items:
                n = (it.get("name") or "").strip()
                r = (it.get("remote") or "").strip()
                if n:
                    covered_names.add(n)
                    covered_names.add(n + ".disabled")
                if r:
                    covered_remotes.add(_normalize_remote(r))

            extras = []
            try:
                entries = [e for e in os.scandir(nodes_dir)
                           if e.is_dir() and not e.name.startswith(".")]
            except Exception:
                return extras

            for e in entries:
                local_name = e.name
                if local_name in covered_names:
                    continue
                # 仅处理 git 仓库（非 git 目录如 __pycache__/example_node 不参与）
                if not os.path.isdir(os.path.join(e.path, ".git")):
                    continue

                code, local_remote, _ = _run_git(e.path, "remote", "get-url", "origin")
                local_remote = local_remote if code == 0 else ""
                if local_remote and _normalize_remote(local_remote) in covered_remotes:
                    continue  # remote 一致：清单覆盖了，但目录被改名 → 不算 extra

                code, local_commit, _ = _run_git(e.path, "rev-parse", "--short", "HEAD")
                local_commit = local_commit if code == 0 else ""

                owner, _repo = _parse_github(local_remote)
                display_name = local_name[:-9] if local_name.endswith(".disabled") else local_name
                extras.append({
                    "name": local_name,
                    "display_name": display_name,
                    "remote": local_remote,
                    "manifest_commit": "", "manifest_branch": "",
                    "author": owner, "installed": True,
                    "local_commit": local_commit, "local_remote": local_remote,
                    "status": "extra",
                })
            return extras

        def build_results():
            rows = [diff_one(it) for it in plugins]
            rows.extend(scan_extras(plugins))
            return rows

        results = await loop.run_in_executor(None, build_results)
        return web.json_response({"status": "success", "results": results})
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


# ================ ComfyUI 本体版本 ================

@routes.get("/extension_manager/comfyui/version")
async def comfyui_version(request):
    """返回 ComfyUI 主仓库的 branch / commit / tag。非 git 部署 → version=None。"""
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _get_comfyui_version)
    return web.json_response({"status": "success", "version": info})


# ================ 自带 ComfyUI 重启（Manager 不在时的兜底） ================

@routes.post("/extension_manager/reboot")
async def self_reboot(request):
    """绕开 ComfyUI-Manager 直接重启 ComfyUI。

    用途：Manager 未安装 / 路径变更（如 cu130-slim-v2 镜像把 Manager 改成 pip 包）
    导致 /manager/reboot 不可用时的兜底。前端 fallback chain 的最后一档。

    实现完全照搬 Manager 的 Legacy execv 逻辑（manager_server.py:1820-1836），
    跨进程行为与 Manager 一致：
    - os.execv 替换当前 Python 进程，容器不退出
    - 不重跑 Docker entrypoint（环境变量改了不会生效）
    - 重启后所有 custom_nodes 重新加载

    安全：与 Manager 的 reboot 同等危险（替换主进程）。不加 security_level
    校验是因为 Koh-ExtensionManager 本身就是"扩展管理器"，调用者已经在管理插件
    生命周期，重启属于其职责范围。仍然依赖 ComfyUI 主进程的访问控制（默认仅
    监听本地或受限网络）。
    """
    try:
        # 关 ComfyUI 自己的日志接管（防止 execv 后 stdout 状态混乱）
        try:
            sys.stdout.close_log()
        except Exception:
            pass

        # 复用 Manager 的命令重建逻辑
        sys_argv = sys.argv.copy()
        if '--windows-standalone-build' in sys_argv:
            sys_argv.remove('--windows-standalone-build')

        if sys_argv[0].endswith("__main__.py"):
            module_name = os.path.basename(os.path.dirname(sys_argv[0]))
            cmds = [sys.executable, '-m', module_name] + sys_argv[1:]
        elif sys.platform.startswith('win32'):
            cmds = ['"' + sys.executable + '"', '"' + sys_argv[0] + '"'] + sys_argv[1:]
        else:
            cmds = [sys.executable] + sys_argv

        print("\n[Koh-ExtensionManager] Restarting ComfyUI (self execv)...\n", flush=True)
        print(f"Command: {cmds}", flush=True)
        os.execv(sys.executable, cmds)
        # execv 替换了进程映像，下面的代码不会执行
        return web.Response(status=200)
    except Exception as e:
        return web.json_response({"status": "error", "msg": str(e)}, status=500)


NODE_CLASS_MAPPINGS = {}
WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "WEB_DIRECTORY"]
