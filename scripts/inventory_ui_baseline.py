"""Offline source inventory. Never imports application config or connects to data."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path


def inventory(root: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    source_files = sorted({*root.joinpath('frontend/src').rglob('*'),
                           *root.joinpath('backend/data_report_api').rglob('*.py')})
    source_files = [p for p in source_files if p.is_file() and p.suffix in {'.vue', '.ts', '.css', '.py'}]
    fingerprints = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in source_files}
    with zipfile.ZipFile(output / 'source-before.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for p in source_files:
            archive.write(p, p.relative_to(root))
    components = []
    for path in source_files:
        if path.suffix != '.vue':
            continue
        source = path.read_text(encoding='utf-8-sig')
        components.append({
            'file': path.relative_to(root).as_posix(),
            'imports': re.findall(r"from\s+['\"]([^'\"]+)['\"]", source),
            'tags': sorted(set(re.findall(r'<([A-Za-z][\w.-]*)\b', source))),
            'operations': [{'line': source.count('\n', 0, m.start()) + 1,
                            'event': m.group(1), 'expression': m.group(2)}
                           for m in re.finditer(r'(@[\w:.-]+|v-model[\w:.-]*)="([^"]*)"', source)],
            'controls': [{'line': source.count('\n', 0, m.start()) + 1, 'tag': m.group(0)}
                         for m in re.finditer(r'<(?:a-button|a-dropdown|a-menu-item|a-tab-pane|FormDialog|a-modal|a-drawer)\b[^>]*>', source)],
            'permissionReferences': [line.strip() for line in source.splitlines()
                                     if re.search(r'permission|isAdmin|menuCode|can[A-Z]', line)],
            'storageReferences': [line.strip() for line in source.splitlines()
                                  if 'localStorage' in line or 'sessionStorage' in line],
        })
    router = root.joinpath('frontend/src/router/index.ts').read_text(encoding='utf-8-sig')
    routes = []
    for number, line in enumerate(router.splitlines(), 1):
        match = re.search(r"\{ path: '([^']+)'", line)
        if match:
            routes.append({'path': match[1], 'line': number, 'declaration': line.strip(),
                           'visualDesktop': '受限：浏览器禁用', 'visualMobile': '受限：浏览器禁用',
                           'interaction': '未执行', 'screenshotBefore': None, 'screenshotAfter': None})
    endpoints = []
    sql_references = []
    metric_references = []
    for path in source_files:
        source = path.read_text(encoding='utf-8-sig')
        relative = path.relative_to(root).as_posix()
        if path.suffix == '.py':
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr in {'get', 'post', 'put', 'patch', 'delete', 'route'}:
                            endpoints.append({'file': relative, 'line': node.lineno, 'handler': node.name,
                                              'declaration': ast.unparse(decorator)})
        for number, line in enumerate(source.splitlines(), 1):
            if re.search(r'\b(?:FROM|JOIN)\s+|TABLE_SPECS|DataSource\(|get_connect\(|raw_connection\(', line, re.I):
                sql_references.append({'file': relative, 'line': number, 'source': line.strip()})
            if re.search(r'formula|指标|\bSUM\(|\bCOUNT\(|\bAVG\(', line, re.I):
                metric_references.append({'file': relative, 'line': number, 'source': line.strip(),
                                          'definitionReview': '待逐项审阅；代码命中不代表业务确认'})
    api_clients = []
    for path in sorted(root.joinpath('frontend/src').rglob('*.ts')):
        for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            if re.search(r'\b(?:http|api|axios)\.(get|post|put|delete|patch)|/api/|/v1/', line):
                api_clients.append({'file': path.relative_to(root).as_posix(), 'line': number, 'source': line.strip()})
    version = subprocess.check_output(['git', '-c', f'safe.directory={root.as_posix()}', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    data = {'version': version, 'scope': '静态源码全量索引；不含真实页面、数据库、运行时生成操作',
            'fingerprints': fingerprints, 'routes': routes, 'components': components,
            'endpoints': endpoints, 'dataSourceReferences': sql_references,
            'metricReferences': metric_references, 'apiClients': api_clients}
    (output / 'inventory.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    rows = ['# 全路由基线与验收入口', '', f'基线 `{version}`。自动提取；动态路由函数需人工复核。',
            '全部页面截图、桌面/移动布局、真实操作目前受浏览器禁用限制，未验。', '',
            '| 路径 | 原始声明（包含组件、权限和别名） | 状态 |', '|---|---|---|']
    for route in routes:
        rows.append(f"| `{route['path']}` | `{route['declaration'].replace('|', '&#124;')}` | 静态已归档 / 动态未验 |")
    (output / 'routes.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    print(json.dumps({'version': version, 'files': len(fingerprints), 'routes': len(routes),
                      'vueComponents': len(components), 'eventBindings': sum(len(c['operations']) for c in components),
                      'endpointDeclarations': len(endpoints), 'dataSourceReferences': len(sql_references),
                      'metricReferences': len(metric_references), 'apiClientReferences': len(api_clients)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inventory(Path(__file__).resolve().parents[1], args.output.resolve())
