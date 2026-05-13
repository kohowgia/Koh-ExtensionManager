import os
import shutil
import subprocess
import asyncio
from aiohttp import web
from server import PromptServer

routes = PromptServer.instance.routes


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


# ================ 路由 ================

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
        return web.json_response({"status": "success", "name": name})
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


NODE_CLASS_MAPPINGS = {}
WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "WEB_DIRECTORY"]
