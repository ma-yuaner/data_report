from __future__ import annotations

from flask import Flask, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from .config import Config
from .routes import api


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)
    app.register_blueprint(api, url_prefix="/api")

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"success": False, "message": "接口不存在", "data": None}), 404

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(_error):
        return jsonify({"success": False, "message": "上传文件超过服务器大小限制", "data": None}), 413

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        app.logger.exception("Unhandled error", exc_info=error)
        return jsonify({"success": False, "message": "服务暂时不可用", "data": None}), 500

    return app
