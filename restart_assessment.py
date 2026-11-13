"""Decide whether a plugin update needs a ComfyUI restart to take effect.

Conservative by design: only a change set made up exclusively of files known to
be frontend / documentation is reported as optional. Anything unrecognised, an
unknown change set, or a first install is "required".
"""
import os

# Backend code and anything that changes the Python environment at startup.
_BACKEND_EXT = {'.py', '.pyi', '.pyx', '.so', '.pyd', '.dll'}
_BACKEND_NAMES = {'requirements.txt', 'install.py', 'pyproject.toml', 'setup.py', 'setup.cfg',
                  'prestartup_script.py', '__init__.py', 'pip.txt'}
# Loaded by the browser on refresh; no server restart needed to serve them.
_FRONTEND_EXT = {'.js', '.mjs', '.css', '.map', '.html', '.svg', '.png', '.jpg', '.jpeg',
                 '.gif', '.webp', '.ico', '.woff', '.woff2', '.ttf', '.vue', '.ts'}
# Pure documentation / repo metadata that nothing loads at runtime.
_DOC_EXT = {'.md', '.rst', '.txt', '.license'}
_DOC_NAMES = {'license', 'licence', 'notice', 'changelog', 'readme', '.gitignore',
              '.gitattributes', '.comfyignore', 'claude.md', 'agents.md'}
_DOC_DIRS = {'docs', 'doc', 'examples', 'example_workflows', 'workflows', 'tests', 'test',
             '.github', '.omo', '.agents', 'assets', 'images'}


def classify_file(path):
    """Return 'backend' | 'frontend' | 'doc' | 'unknown' for one repo-relative path."""
    norm = path.replace('\\', '/').strip('/')
    parts = norm.split('/')
    base = parts[-1].lower()
    ext = os.path.splitext(base)[1]
    if base in _BACKEND_NAMES or ext in _BACKEND_EXT:
        # Tests and docs folders may hold .py that nothing imports at startup.
        if parts[0].lower() in {'tests', 'test', 'docs', 'doc', '.github', 'examples', 'scripts'} and base != 'requirements.txt':
            return 'doc'
        return 'backend'
    if parts[0].lower() in _DOC_DIRS and ext not in {'.js', '.css'}:
        return 'doc'
    if base in _DOC_NAMES or ext in _DOC_EXT:
        return 'doc'
    if ext in _FRONTEND_EXT:
        # A frontend file outside a conventional web folder may be read by the backend.
        return 'frontend'
    return 'unknown'


def assess_restart(changed_files, *, first_install=False, dependencies_changed=False):
    """Return {'level': 'required'|'optional', 'reason': str, 'files': [...]}."""
    if first_install:
        return {'level': 'required', 'reason': '新装插件，新节点需重启后才会出现', 'files': []}
    if dependencies_changed:
        return {'level': 'required', 'reason': 'Python 依赖已变化，需重启加载', 'files': []}
    if changed_files is None:
        return {'level': 'required', 'reason': '无法确定改动文件，保守按必须重启处理', 'files': []}
    files = [f for f in changed_files if f]
    if not files:
        return {'level': 'optional', 'reason': '代码没有变化', 'files': []}
    classes = {f: classify_file(f) for f in files}
    backend = [f for f, c in classes.items() if c == 'backend']
    unknown = [f for f, c in classes.items() if c == 'unknown']
    if backend:
        return {'level': 'required', 'reason': '后端文件已更新：' + '、'.join(backend[:3]) + ('等' if len(backend) > 3 else ''), 'files': files[:50]}
    if unknown:
        return {'level': 'required', 'reason': '含无法判断的文件：' + '、'.join(unknown[:3]), 'files': files[:50]}
    return {'level': 'optional', 'reason': '仅前端或文档更新，刷新浏览器即可，重启非必须', 'files': files[:50]}
