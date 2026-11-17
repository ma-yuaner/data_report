"""Short-lived login challenges shared by workers on one application host.

SQLite table/column dictionary: docs/development/login-brand-captcha-20261117.md.
Only digests are retained; neither answers nor browser tokens are logged.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import closing

from PIL import Image, ImageDraw, ImageFont

from .auth import AuthError


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class LoginCaptcha:
    TTL = 180
    COOKIE = "data_report_captcha"

    def __init__(self, root: str):
        self.path = Path(root) / "challenges.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript("""
                -- 登录浏览器当前有效挑战，每个浏览器仅保留一条。
                CREATE TABLE IF NOT EXISTS login_captcha (
                    browser_hash TEXT PRIMARY KEY,
                    challenge_id TEXT NOT NULL,
                    answer_hash TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                -- 验证码签发频率窗口，不存储原始IP。
                CREATE TABLE IF NOT EXISTS login_captcha_rate (
                    scope_hash TEXT PRIMARY KEY,
                    hits INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    @staticmethod
    def image(answer: str) -> str:
        image = Image.new("RGB", (144, 52), "#eef8f8")
        draw = ImageDraw.Draw(image)
        rng = secrets.SystemRandom()
        for _ in range(7):
            draw.line((rng.randrange(144), rng.randrange(52), rng.randrange(144), rng.randrange(52)), fill="#b3d8db")
        font = ImageFont.load_default(size=30)
        for index, character in enumerate(answer):
            draw.text((12 + index * 32, rng.randrange(5, 13)), character, fill="#236b74", font=font)
        for _ in range(65):
            draw.point((rng.randrange(144), rng.randrange(52)), fill="#83b8bd")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")

    def issue(self, browser: str, address: str) -> dict:
        now = int(time.time())
        challenge_id = secrets.token_urlsafe(24)
        answer = "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4))
        image = self.image(answer)
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_captcha WHERE expires_at <= ?", (now,))
            db.execute("DELETE FROM login_captcha_rate WHERE expires_at <= ?", (now,))
            for scope, limit in (("browser:" + browser, 20), ("peer:" + address, 120)):
                key = digest(scope)
                row = db.execute("SELECT hits FROM login_captcha_rate WHERE scope_hash = ?", (key,)).fetchone()
                if row and row[0] >= limit:
                    raise AuthError("验证码刷新过于频繁，请稍后再试", 429, "CAPTCHA_RATE_LIMIT")
                db.execute("""INSERT INTO login_captcha_rate VALUES (?, 1, ?)
                    ON CONFLICT(scope_hash) DO UPDATE SET hits = hits + 1""", (key, now + 60))
            if db.execute("SELECT COUNT(*) FROM login_captcha").fetchone()[0] >= 10000:
                raise AuthError("验证码服务繁忙，请稍后重试", 503, "CAPTCHA_UNAVAILABLE")
            db.execute("INSERT OR REPLACE INTO login_captcha VALUES (?, ?, ?, ?)",
                       (digest(browser), challenge_id, digest(challenge_id + answer), now + self.TTL))
        return {"challengeId": challenge_id, "image": image, "expiresIn": self.TTL}

    def verify(self, browser: str, challenge_id: str, answer: str) -> None:
        if not browser or not challenge_id or len(challenge_id) > 100:
            raise AuthError("请刷新并输入图形验证码", 400, "CAPTCHA_INVALID")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT challenge_id, answer_hash, expires_at FROM login_captcha WHERE browser_hash = ?",
                             (digest(browser),)).fetchone()
            # Consume before checking the answer; commit also on a wrong answer.
            if row and hmac.compare_digest(row[0], challenge_id):
                db.execute("DELETE FROM login_captcha WHERE browser_hash = ?", (digest(browser),))
            else:
                row = None
        if not row or row[2] <= int(time.time()):
            raise AuthError("验证码已失效，请刷新后重试", 400, "CAPTCHA_EXPIRED")
        if len(answer) != 4 or not hmac.compare_digest(row[1], digest(challenge_id + answer.upper())):
            raise AuthError("验证码不正确，请重新输入", 400, "CAPTCHA_INVALID")
