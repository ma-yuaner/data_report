"""Documentation scanner tests: no Flask import, database, or network required."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_readme as checker


class ReadmeScannerTests(unittest.TestCase):
    def setUp(self):
        artifacts = Path(__file__).resolve().parents[2] / ".test-artifacts"
        artifacts.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="readme-check-", dir=artifacts)
        self.root = Path(temporary.name).resolve()
        if not self.root.is_relative_to(artifacts.resolve()):
            raise RuntimeError("Test cleanup target must remain inside task artifacts")
        self.addCleanup(temporary.cleanup)

    def write(self, filename, text):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def fixture(self):
        self.write(
            "backend/data_report_api/__init__.py",
            """
raise RuntimeError("Scanner must never execute app initialization")
app.register_blueprint(api, url_prefix="/api")
app.register_blueprint(auth_api, url_prefix="/api")
""",
        )
        self.write("backend/data_report_api/routes.py", "from .api import widgets\nwidgets.register_routes(api)\n")
        self.write(
            "backend/data_report_api/api/widgets.py",
            """
def register_routes(api):
    @api.get("/v1/widgets/<int:item_id>")
    def widget(item_id): pass
""",
        )
        self.write(
            "backend/data_report_api/api/unregistered.py",
            """
@api.post("/v1/unregistered")
def invisible(): pass
""",
        )
        self.write(
            "backend/data_report_api/auth_routes.py",
            """
@auth_api.errorhandler(ValueError)
def error_handler(): pass
@auth_api.get("/auth/status")
def status(): pass
""",
        )
        self.write(
            "frontend/src/layouts/AppLayout.vue", '<a-menu><a-menu-item key="/home">工作台</a-menu-item></a-menu>'
        )
        self.write(
            "README.md",
            "产品说明保留\n<!-- BEGIN:CURRENT_MENU -->\n<!-- END:CURRENT_MENU -->\n<!-- BEGIN:API_SUMMARY -->\n<!-- END:API_SUMMARY -->\n",
        )
        self.write("docs/api/README.md", "人工维护接口说明\n<!-- BEGIN:API_ROUTES -->\n<!-- END:API_ROUTES -->\n")

    def run_cli(self, *arguments):
        with patch.object(checker, "ROOT", self.root), patch("sys.argv", ["check_readme.py", *arguments]):
            with contextlib.redirect_stdout(io.StringIO()):
                return checker.main()

    def test_methods_dynamic_paths_and_non_route_decorators(self):
        endpoints = checker.parse_endpoints(
            """
@api.route("/items/<int:item_id>", methods=["GET", "PATCH"])
def item(item_id): pass
@api.errorhandler(ValueError)
def error(): pass
""",
            owner="api",
            prefix="/api",
            group="items",
            filename="routes.py",
        )
        self.assertEqual(
            [(item.method, item.path) for item in endpoints],
            [("GET", "/api/items/<int:item_id>"), ("PATCH", "/api/items/<int:item_id>")],
        )

    def test_dynamic_or_invalid_methods_do_not_silently_disappear(self):
        with self.assertRaises(ValueError):
            checker.parse_endpoints(
                '@api.route("/x", methods=runtime_methods)\ndef x(): pass',
                owner="api",
                prefix="/api",
                group="x",
                filename="x.py",
            )
        with self.assertRaises(ValueError):
            checker.parse_endpoints(
                '@api.route("/x", methods=["INVALID"])\ndef x(): pass',
                owner="api",
                prefix="/api",
                group="x",
                filename="x.py",
            )

    def test_only_registered_sources_are_read_without_importing_app(self):
        self.fixture()
        endpoints = checker.read_endpoints(self.root)
        self.assertEqual({item.path for item in endpoints}, {"/api/auth/status", "/api/v1/widgets/<int:item_id>"})

    def test_new_blueprint_and_duplicate_routes_require_attention(self):
        self.fixture()
        path = self.root / "backend/data_report_api/api/widgets.py"
        path.write_text(
            path.read_text(encoding="utf-8") + '\n@api.get("/v1/widgets/<int:item_id>")\ndef duplicate(): pass\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "重复"):
            checker.read_endpoints(self.root)
        self.write("backend/data_report_api/__init__.py", 'app.register_blueprint(new_api, url_prefix="/api")\n')
        with self.assertRaisesRegex(ValueError, "蓝图集合"):
            checker.read_endpoints(self.root)
        self.fixture()
        self.write("backend/data_report_api/routes.py", "from .api import widgets\nregister_widgets(api)\n")
        with self.assertRaisesRegex(ValueError, "注册未完整识别"):
            checker.read_endpoints(self.root)

    def test_sidebar_includes_nested_disabled_items_but_not_account_dropdown(self):
        self.write(
            "frontend/src/layouts/AppLayout.vue",
            """
<a-menu><a-sub-menu key="smart"><template #title>智能分析</template>
<a-sub-menu key="overall"><template #title>智能整体分析</template>
<a-menu-item key="/smart-analysis/overview">智能总览</a-menu-item></a-sub-menu>
<a-menu-item key="reserved" disabled>预留功能</a-menu-item></a-sub-menu></a-menu>
<a-menu><a-menu-item key="logout">退出登录</a-menu-item></a-menu>
""",
        )
        menu = checker.read_menu(self.root)
        self.assertEqual(len(menu), 2)
        self.assertEqual(menu[0].groups, ("智能分析", "智能整体分析"))
        self.assertTrue(menu[1].disabled)
        self.assertIn("预留/禁用", checker.render_menu(menu))

    def test_generated_blocks_preserve_human_content_and_reject_bad_markers(self):
        text = "before\n<!-- BEGIN:X -->\nold\n<!-- END:X -->\nafter\n"
        self.assertEqual(checker.replace_block(text, "X", "new"), text.replace("old", "new"))
        with self.assertRaises(ValueError):
            checker.replace_block(text + "<!-- BEGIN:X -->", "X", "new")

    def test_default_check_is_read_only_and_detects_new_routes_after_refresh(self):
        self.fixture()
        before = (self.root / "README.md").read_bytes()
        self.assertEqual(self.run_cli(), 1)
        self.assertEqual((self.root / "README.md").read_bytes(), before)
        self.assertEqual(self.run_cli("--write"), 0)
        self.assertEqual(self.run_cli("--check"), 0)
        self.assertIn("产品说明保留", (self.root / "README.md").read_text(encoding="utf-8"))
        path = self.root / "backend/data_report_api/api/widgets.py"
        path.write_text(
            path.read_text(encoding="utf-8") + '\n@api.post("/v1/widgets")\ndef create(): pass\n', encoding="utf-8"
        )
        self.assertEqual(self.run_cli("--check"), 1)


if __name__ == "__main__":
    unittest.main()
