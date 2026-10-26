"""Check or refresh README menu/API inventories without importing the application."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "route"}
GROUPS = {
    "auth": "账号认证与权限管理",
    "core": "基础信息、资产与兼容入口",
    "dashboard": "经营总览与利润核对",
    "analysis": "业务、风控分析与问题中心",
    "resource_governance": "GDS/OTA资源治理与航线诊断",
    "smart_analysis": "智能分析、导出与视图模板",
    "smart_placement": "智能投放与收单",
    "monitoring": "监控、规则、事件、工单与通知",
    "targets": "目标配置、进度与刷新",
    "risk_upload": "风控文件上传",
    "data_workbench": "数据加工工作台",
    "hr_mail": "HR报表邮件",
    "telemetry": "行为采集与管理看板",
}


@dataclass(frozen=True)
class MenuItem:
    groups: tuple[str, ...]
    label: str
    key: str
    disabled: bool


@dataclass(frozen=True)
class Endpoint:
    group: str
    method: str
    path: str
    handler: str
    source: str


class MenuParser(HTMLParser):
    """Read the first sidebar a-menu, excluding the separate account dropdown."""

    def __init__(self):
        super().__init__()
        self.started = False
        self.active = False
        self.groups: list[dict[str, str]] = []
        self.title_group: dict[str, str] | None = None
        self.item: dict | None = None
        self.items: list[MenuItem] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a-menu" and not self.started:
            self.started = self.active = True
        if not self.active:
            return
        if tag == "a-sub-menu":
            self.groups.append({"title": ""})
        elif tag == "template" and "#title" in values and self.groups:
            self.title_group = self.groups[-1]
        elif tag == "a-menu-item":
            if not values.get("key"):
                raise ValueError("菜单包含非静态key，需要补充脚本解析规则")
            if any(not group["title"].strip() for group in self.groups):
                raise ValueError("菜单组标题不是可读取的静态标题")
            if ":disabled" in values:
                raise ValueError("菜单使用动态disabled，需要人工确认并扩展脚本")
            self.item = {"key": values["key"], "disabled": "disabled" in values, "text": []}

    def handle_data(self, data):
        if not self.active:
            return
        if self.item is not None:
            self.item["text"].append(data)
        elif self.title_group is not None:
            self.title_group["title"] += data

    def handle_endtag(self, tag):
        if not self.active:
            return
        if tag == "a-menu-item" and self.item is not None:
            label = " ".join("".join(self.item["text"]).split())
            if not label or "{{" in label:
                raise ValueError("菜单标题不是可读取的静态文本")
            self.items.append(
                MenuItem(
                    tuple(group["title"].strip() for group in self.groups),
                    label,
                    self.item["key"],
                    self.item["disabled"],
                )
            )
            self.item = None
        elif tag == "template":
            self.title_group = None
        elif tag == "a-sub-menu":
            self.groups.pop()
        elif tag == "a-menu":
            self.active = False


def read_menu(root: Path) -> list[MenuItem]:
    parser = MenuParser()
    parser.feed((root / "frontend/src/layouts/AppLayout.vue").read_text(encoding="utf-8-sig"))
    if not parser.items:
        raise ValueError("未读取到实际侧栏菜单，拒绝生成空目录")
    keys = [item.key for item in parser.items]
    if len(keys) != len(set(keys)):
        raise ValueError("侧栏存在重复菜单key")
    return parser.items


def parse_endpoints(source: str, *, owner: str, prefix: str, group: str, filename: str) -> list[Endpoint]:
    endpoints = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in function.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            call = decorator.func
            if not isinstance(call.value, ast.Name) or call.value.id != owner or call.attr not in METHODS:
                continue
            if not decorator.args:
                raise ValueError(f"{filename}:{function.name}: 路由缺少静态路径")
            path = ast.literal_eval(decorator.args[0])
            if not isinstance(path, str) or not path.startswith("/"):
                raise ValueError(f"{filename}:{function.name}: 路径必须为静态绝对路径")
            methods = [call.attr.upper()]
            if call.attr == "route":
                method_arg = next((arg.value for arg in decorator.keywords if arg.arg == "methods"), None)
                methods = ast.literal_eval(method_arg) if method_arg is not None else ["GET"]
                if not isinstance(methods, (list, tuple)) or not methods:
                    raise ValueError(f"{filename}:{function.name}: methods必须为非空静态列表")
            for method in methods:
                if not isinstance(method, str) or method.lower() not in METHODS - {"route"}:
                    raise ValueError(f"{filename}:{function.name}: 未支持的HTTP方法")
                endpoints.append(Endpoint(group, method.upper(), prefix.rstrip("/") + path, function.name, filename))
    return endpoints


def read_endpoints(root: Path) -> list[Endpoint]:
    package = root / "backend/data_report_api"
    app_source = (package / "__init__.py").read_text(encoding="utf-8-sig")
    app_tree = ast.parse(app_source)
    prefixes = {}
    for node in ast.walk(app_tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "register_blueprint"
        ):
            if not node.args or not isinstance(node.args[0], ast.Name):
                raise ValueError("蓝图注册方式已变化，需要更新文档扫描脚本")
            value = next((arg.value for arg in node.keywords if arg.arg == "url_prefix"), None)
            prefixes[node.args[0].id] = ast.literal_eval(value) if value is not None else ""
    if set(prefixes) != {"api", "auth_api"}:
        raise ValueError(f"蓝图集合已变化，需要更新扫描脚本：{sorted(prefixes)}")

    registry = ast.parse((package / "routes.py").read_text(encoding="utf-8-sig"))
    imports = {}
    for node in registry.body:
        if isinstance(node, ast.ImportFrom) and node.module == "api" and node.level == 1:
            imports.update({alias.asname or alias.name: alias.name for alias in node.names})
    sources = [("auth", package / "auth_routes.py", "auth_api", prefixes["auth_api"])]
    registered = set()
    for node in registry.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if isinstance(call.func, ast.Attribute) and call.func.attr == "register_routes":
            if not isinstance(call.func.value, ast.Name) or call.func.value.id not in imports:
                raise ValueError("领域路由注册方式已变化，需要更新扫描脚本")
            if len(call.args) != 1 or not isinstance(call.args[0], ast.Name) or call.args[0].id != "api":
                raise ValueError("领域路由绑定的蓝图已变化，需要更新扫描脚本")
            name = imports[call.func.value.id]
            registered.add(call.func.value.id)
            sources.append((name, package / "api" / f"{name}.py", "api", prefixes["api"]))
    if not imports or registered != set(imports):
        raise ValueError("领域注册未完整识别，拒绝生成不完整接口目录；请更新扫描脚本")
    endpoints = parse_endpoints(
        app_source, owner="app", prefix="", group="app", filename="backend/data_report_api/__init__.py"
    )
    for group, path, owner, prefix in sources:
        endpoints.extend(
            parse_endpoints(
                path.read_text(encoding="utf-8-sig"),
                owner=owner,
                prefix=prefix,
                group=group,
                filename=path.relative_to(root).as_posix(),
            )
        )
    identities = [(item.method, item.path) for item in endpoints]
    if not endpoints or len(identities) != len(set(identities)):
        raise ValueError("接口集合为空或存在重复方法/路径，请核查注册源")
    return endpoints


def render_menu(items: list[MenuItem]) -> str:
    disabled = sum(item.disabled for item in items)
    lines = [
        "<details>",
        f"<summary>完整菜单：{len(items) - disabled}个页面入口、{disabled}个禁用预留项</summary>",
        "",
        "```text",
    ]
    previous: tuple[str, ...] = ()
    for item in items:
        common = 0
        while common < min(len(previous), len(item.groups)) and previous[common] == item.groups[common]:
            common += 1
        for depth in range(common, len(item.groups)):
            lines.append("  " * depth + item.groups[depth])
        target = "预留/禁用，无页面路由" if item.disabled else item.key
        lines.append("  " * len(item.groups) + f"{item.label}  [{target}]")
        previous = item.groups
    return "\n".join(lines + ["```", "", "</details>"])


def group_order(endpoints: list[Endpoint]) -> list[str]:
    return sorted(
        {item.group for item in endpoints},
        key=lambda name: (list(GROUPS).index(name) if name in GROUPS else len(GROUPS), name),
    )


def render_summary(endpoints: list[Endpoint]) -> str:
    counts = Counter(item.group for item in endpoints)
    lines = [
        f"当前静态登记 **{len(endpoints)}个HTTP方法/路径条目**（含认证与管理接口，不重复列自动HEAD/OPTIONS）。",
        "",
        "| 接口领域 | 条目数 | 完整清单 |",
        "|---|---:|---|",
    ]
    for name in group_order(endpoints):
        lines.append(f"| {GROUPS.get(name, name)} | {counts[name]} | [{name}](docs/api/README.md#{name}) |")
    return "\n".join(lines)


def render_api(endpoints: list[Endpoint]) -> str:
    lines = [f"共 **{len(endpoints)}个HTTP方法/路径条目**。方法和动态路径参数保留源码写法。"]
    for name in group_order(endpoints):
        lines.extend(
            [
                "",
                f'<a id="{name}"></a>',
                "",
                f"## {GROUPS.get(name, name)}（{name}）",
                "",
                "| 方法 | 完整路径 | 处理函数 / 源码 |",
                "|---|---|---|",
            ]
        )
        for item in sorted(
            (item for item in endpoints if item.group == name), key=lambda item: (item.path, item.method)
        ):
            lines.append(f"| `{item.method}` | `{item.path}` | [{item.handler}](../../{item.source}) |")
    return "\n".join(lines)


def replace_block(content: str, name: str, rendered: str) -> str:
    start = f"<!-- BEGIN:{name} -->"
    end = f"<!-- END:{name} -->"
    if content.count(start) != 1 or content.count(end) != 1 or content.index(start) > content.index(end):
        raise ValueError(f"生成标记缺失、重复或顺序错误：{name}")
    first = content.index(start) + len(start)
    last = content.index(end)
    return content[:first] + "\n" + rendered + "\n" + content[last:]


def plan_updates(root: Path, items: list[MenuItem], endpoints: list[Endpoint]) -> dict[Path, str]:
    readme = root / "README.md"
    catalog = root / "docs/api/README.md"
    text = readme.read_text(encoding="utf-8-sig")
    text = replace_block(text, "CURRENT_MENU", render_menu(items))
    text = replace_block(text, "API_SUMMARY", render_summary(endpoints))
    api_text = replace_block(catalog.read_text(encoding="utf-8-sig"), "API_ROUTES", render_api(endpoints))
    return {readme: text, catalog: api_text}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Only report inventory drift (default)")
    mode.add_argument("--write", action="store_true", help="Refresh generated menu/API blocks only")
    args = parser.parse_args()
    try:
        items = read_menu(ROOT)
        endpoints = read_endpoints(ROOT)
        updates = plan_updates(ROOT, items, endpoints)
        changed = [path for path, content in updates.items() if path.read_text(encoding="utf-8-sig") != content]
        for path in changed:
            if args.write:
                path.write_text(updates[path], encoding="utf-8", newline="\n")
                print(f"Updated: {path.relative_to(ROOT).as_posix()}")
            else:
                print(f"Out of date: {path.relative_to(ROOT).as_posix()} (run --write, then review product content)")
        if changed and not args.write:
            return 1
        print(f"README inventories verified: {len(items)} menu entries; {len(endpoints)} HTTP method/path entries")
        return 0
    except (ValueError, OSError, SyntaxError) as error:
        print(f"README check failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
