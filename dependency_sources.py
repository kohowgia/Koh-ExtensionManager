"""Static custom-node dependency provenance. Read-only: parses declared files,
never executes install.py or imports third-party plugin code."""
import os
import re
import ast
try:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
except ImportError:
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name

MAX_FILE = 512 * 1024

def _reqs_from_text(text, source):
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or line.startswith(('-r ', '--')):
            continue
        try:
            req = Requirement(line)
            rows.append({'name': canonicalize_name(req.name), 'requirement': line, 'source': source})
        except Exception:
            pass
    return rows

def _read(path):
    try:
        if os.path.getsize(path) > MAX_FILE:
            return ''
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''

def scan(root):
    if not isinstance(root, str) or not os.path.isdir(root):
        raise ValueError('自定义节点目录不可用')
    result = []
    for name in sorted(os.listdir(root)):
        if name.startswith('.') or name.endswith('.disabled'):
            continue
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        rows = []
        req = os.path.join(folder, 'requirements.txt')
        if os.path.isfile(req):
            rows += _reqs_from_text(_read(req), 'requirements.txt')
        pyproject = os.path.join(folder, 'pyproject.toml')
        if os.path.isfile(pyproject):
            # Conservative static parser: only PEP 621 dependency string lines.
            in_deps = False
            for raw in _read(pyproject).splitlines():
                line = raw.strip()
                if line.startswith('dependencies') and '=' in line:
                    in_deps = True
                if in_deps:
                    for quoted in re.findall(r"['\"]([^'\"]+)['\"]", line):
                        rows += _reqs_from_text(quoted, 'pyproject.toml')
                    if ']' in line: in_deps = False
        # install.py can construct shell commands dynamically. Do not attempt to
        # infer a dependency from source text: false provenance is worse than an
        # explicit "unconfirmed" result. It is deliberately never executed.
        if rows:
            unique = {(r['name'], r['requirement'], r['source']): r for r in rows}
            result.append({'plugin': name, 'requirements': list(unique.values())})
    return {'plugins': result, 'note': '仅扫描 requirements.txt、pyproject.toml 和 install.py 的可静态识别内容；不会执行插件代码，无法证明未声明依赖的来源。'}
