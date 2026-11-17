"""Run the real ADM parsing product on loopback, with isolated files and SQLite.

Never loads the production .env, never connects to business databases. API calls
are disabled unless --allow-configured-api is explicitly supplied. Build the
normal frontend first. This runner is for local acceptance, not deployment.
"""
import argparse
import sys
import threading
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-packages", help="Optional existing local virtualenv site-packages")
    parser.add_argument("--root", help="Isolated parsing files/database directory")
    parser.add_argument("--allow-configured-api", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "backend"))
    if args.site_packages:
        sys.path.append(str(Path(args.site_packages).resolve()))
    from flask import abort, jsonify, request, send_from_directory
    from werkzeug.serving import make_server
    from data_report_api import create_app
    from data_report_api.config import Config

    root = Path(args.root).resolve() if args.root else repo / ".test-artifacts/adm-parsing-local"
    dist = repo / "frontend/dist"
    if not (dist / "index.html").is_file():
        parser.error("Build the frontend first; frontend/dist/index.html is missing")

    class LocalConfig(Config):
        TESTING = True
        DEBUG = False
        AUTH_ENABLED = False
        DATA_MODE = "mock"
        MYSQL_HOST = ADM_MYSQL_HOST = ERP_MYSQL_HOST = HOTEL_MYSQL_HOST = FI_MYSQL_HOST = ""
        ADM_PARSING_STORAGE_MODE = "sqlite"
        ADM_PARSING_SQLITE_PATH = str(root / "parsing.sqlite3")
        ADM_PARSING_ROOT = str(root / "files")
        ADM_PARSING_AI_ENABLED = Config.ADM_PARSING_AI_ENABLED if args.allow_configured_api else False

    app = create_app(LocalConfig)

    @app.before_request
    def isolate_local_api():
        if request.path.startswith("/api/") and not request.path.startswith("/api/v1/adm/parsing/") and request.path not in {"/api/health", "/api/auth/me", "/api/auth/status", "/api/auth/logout"}:
            return jsonify(success=False, data=None, message="本地隔离环境仅启用ADM解析；其他业务未连接", code="LOCAL_SCOPE_ONLY"), 503

    @app.get("/")
    @app.get("/<path:path>")
    def local_frontend(path=""):
        if path.startswith("api/"):
            abort(404)
        if path and (dist / path).is_file():
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")

    # Bind both existing local ports only to loopback; fail instead of replacing other services.
    web = make_server("127.0.0.1", 1818, app, threaded=True)
    api = make_server("127.0.0.1", 5160, app, threaded=True)
    thread = threading.Thread(target=api.serve_forever, daemon=True)
    thread.start()
    print("Local product: http://127.0.0.1:1818/adm/parsing | API: 127.0.0.1:5160", flush=True)
    print("Isolated SQLite and real file processing; production DB disabled; API enabled only by explicit flag.", flush=True)
    try:
        web.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        web.server_close()
        api.shutdown()
        api.server_close()


if __name__ == "__main__":
    main()
