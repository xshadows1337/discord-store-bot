"""
AbyssHub User Authentication System
SQLite-backed user accounts with JWT tokens and Mailgun email verification.
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

import aiohttp
from loguru import logger

# ── Config ────────────────────────────────────────────────────────────────────
_DB_PATH = Path(__file__).parent.parent / 'users.db'
_JWT_SECRET = os.environ.get('JWT_SECRET', secrets.token_hex(32))
_JWT_TTL = 7 * 24 * 3600   # 7 days

MAILGUN_API_KEY = os.environ.get('MAILGUN_API_KEY', '9701916f5c5ba8bad39c35064e29a9ab-f39109fe-25fcbd0d')
MAILGUN_DOMAIN  = os.environ.get('MAILGUN_DOMAIN', 'pay.xshadows.shop')
MAILGUN_FROM    = f'AbyssHub <noreply@{MAILGUN_DOMAIN}>'

# ── SQLite init ───────────────────────────────────────────────────────────────
_conn: sqlite3.Connection | None = None

def _get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute('PRAGMA journal_mode=WAL')
        _conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                email           TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                password_hash   TEXT    NOT NULL,
                salt            TEXT    NOT NULL,
                email_verified  INTEGER NOT NULL DEFAULT 0,
                verify_code     TEXT,
                reset_code      TEXT,
                reset_expiry    REAL,
                created_at      REAL    NOT NULL DEFAULT (strftime('%s','now'))
            )
        ''')
        _conn.commit()
    return _conn

# ── Password hashing (SHA-256 + salt – no bcrypt dependency) ──────────────────

def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 120_000)
    return h.hex(), salt

def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    h, _ = _hash_password(password, salt)
    return hmac.compare_digest(h, stored_hash)

# ── Minimal JWT (no PyJWT dependency) ─────────────────────────────────────────

import base64

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def _b64url_decode(s: str) -> bytes:
    s += '=' * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)

def create_token(user_id: int, username: str) -> str:
    header = _b64url(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
    payload = _b64url(json.dumps({
        'uid': user_id,
        'usr': username,
        'exp': time.time() + _JWT_TTL,
    }).encode())
    sig = _b64url(hmac.new(_JWT_SECRET.encode(), f'{header}.{payload}'.encode(), hashlib.sha256).digest())
    return f'{header}.{payload}.{sig}'

def verify_token(token: str) -> dict | None:
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        expected_sig = _b64url(hmac.new(_JWT_SECRET.encode(), f'{header}.{payload}'.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data = json.loads(_b64url_decode(payload))
        if data.get('exp', 0) < time.time():
            return None
        return data
    except Exception:
        return None

# ── User CRUD ─────────────────────────────────────────────────────────────────

def register_user(username: str, email: str, password: str) -> tuple[bool, str, int | None]:
    """Returns (success, message, user_id)."""
    db = _get_db()
    # Validate
    if len(username) < 3 or len(username) > 20:
        return False, 'Username must be 3-20 characters.', None
    if not all(c.isalnum() or c in '_-.' for c in username):
        return False, 'Username may only contain letters, numbers, _, -, and dots.', None
    if len(password) < 6:
        return False, 'Password must be at least 6 characters.', None
    if '@' not in email or '.' not in email:
        return False, 'Invalid email address.', None

    pw_hash, salt = _hash_password(password)
    verify_code = secrets.token_hex(3).upper()  # 6-char hex code

    try:
        cur = db.execute(
            'INSERT INTO users (username, email, password_hash, salt, verify_code) VALUES (?, ?, ?, ?, ?)',
            (username, email.lower(), pw_hash, salt, verify_code),
        )
        db.commit()
        return True, verify_code, cur.lastrowid
    except sqlite3.IntegrityError as e:
        err = str(e).lower()
        if 'username' in err:
            return False, 'Username already taken.', None
        if 'email' in err:
            return False, 'Email already registered.', None
        return False, 'Registration failed.', None

def login_user(email: str, password: str) -> tuple[bool, str, str | None]:
    """Returns (success, message, token)."""
    db = _get_db()
    row = db.execute('SELECT * FROM users WHERE email = ?', (email.lower(),)).fetchone()
    if not row:
        return False, 'Invalid email or password.', None
    if not _verify_password(password, row['password_hash'], row['salt']):
        return False, 'Invalid email or password.', None
    if not row['email_verified']:
        return False, 'Please verify your email first. Check your inbox.', None
    token = create_token(row['id'], row['username'])
    return True, row['username'], token

def verify_email(email: str, code: str) -> tuple[bool, str, str | None, str | None]:
    """Returns (success, message, token, username).  token/username are None on failure."""
    db = _get_db()
    row = db.execute('SELECT * FROM users WHERE email = ?', (email.lower(),)).fetchone()
    if not row:
        return False, 'Email not found.', None, None
    if row['email_verified']:
        token = create_token(row['id'], row['username'])
        return True, 'Email already verified.', token, row['username']
    if (row['verify_code'] or '').upper() != code.upper():
        return False, 'Invalid verification code.', None, None
    db.execute('UPDATE users SET email_verified = 1, verify_code = NULL WHERE id = ?', (row['id'],))
    db.commit()
    token = create_token(row['id'], row['username'])
    return True, 'Email verified successfully.', token, row['username']

def request_password_reset(email: str) -> tuple[bool, str, str | None]:
    """Returns (success, message, reset_code)."""
    db = _get_db()
    row = db.execute('SELECT * FROM users WHERE email = ?', (email.lower(),)).fetchone()
    if not row:
        # Don't reveal whether email exists
        return True, 'If that email exists, a reset code has been sent.', None
    code = secrets.token_hex(3).upper()
    db.execute(
        'UPDATE users SET reset_code = ?, reset_expiry = ? WHERE id = ?',
        (code, time.time() + 900, row['id']),  # 15 min expiry
    )
    db.commit()
    return True, 'Reset code sent.', code

def reset_password(email: str, code: str, new_password: str) -> tuple[bool, str]:
    db = _get_db()
    row = db.execute('SELECT * FROM users WHERE email = ?', (email.lower(),)).fetchone()
    if not row:
        return False, 'Invalid reset request.'
    if not row['reset_code'] or row['reset_code'].upper() != code.upper():
        return False, 'Invalid reset code.'
    if (row['reset_expiry'] or 0) < time.time():
        return False, 'Reset code has expired. Request a new one.'
    if len(new_password) < 6:
        return False, 'Password must be at least 6 characters.'
    pw_hash, salt = _hash_password(new_password)
    db.execute(
        'UPDATE users SET password_hash = ?, salt = ?, reset_code = NULL, reset_expiry = NULL WHERE id = ?',
        (pw_hash, salt, row['id']),
    )
    db.commit()
    return True, 'Password reset successful. You can now log in.'

def get_user_by_id(user_id: int) -> dict | None:
    db = _get_db()
    row = db.execute('SELECT id, username, email, email_verified, created_at FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        return None
    return dict(row)

# ── Mailgun email sending ────────────────────────────────────────────────────

async def send_verification_email(to_email: str, code: str):
    html = f'''
    <div style="background:#111;color:#fff;font-family:Arial,sans-serif;max-width:500px;margin:0 auto;padding:2rem;border:1px solid #333;border-radius:8px;">
      <div style="text-align:center;margin-bottom:1.5rem;">
        <span style="font-size:1.6rem;font-weight:900;color:#fff;">ABYSS</span><span style="background:#ff9000;color:#000;border-radius:4px;padding:2px 10px;font-size:1.6rem;font-weight:900;margin-left:3px;">HUB</span>
      </div>
      <h2 style="text-align:center;font-size:1.2rem;margin-bottom:1rem;">Verify Your Email</h2>
      <p style="color:#aaa;font-size:.9rem;line-height:1.6;text-align:center;">Use the code below to verify your AbyssHub account:</p>
      <div style="background:#ff9000;color:#000;font-size:1.8rem;font-weight:900;text-align:center;padding:.8rem;border-radius:6px;letter-spacing:.3em;margin:1.5rem 0;">
        {code}
      </div>
      <p style="color:#666;font-size:.75rem;text-align:center;">This code expires in 24 hours. If you didn't create an account, ignore this email.</p>
      <div style="text-align:center;margin-top:1.5rem;color:#333;font-size:.7rem;">&copy; 2026 AbyssHub</div>
    </div>
    '''
    await _send_mailgun(to_email, 'AbyssHub — Verify your email', html)

async def send_reset_email(to_email: str, code: str):
    html = f'''
    <div style="background:#111;color:#fff;font-family:Arial,sans-serif;max-width:500px;margin:0 auto;padding:2rem;border:1px solid #333;border-radius:8px;">
      <div style="text-align:center;margin-bottom:1.5rem;">
        <span style="font-size:1.6rem;font-weight:900;color:#fff;">ABYSS</span><span style="background:#ff9000;color:#000;border-radius:4px;padding:2px 10px;font-size:1.6rem;font-weight:900;margin-left:3px;">HUB</span>
      </div>
      <h2 style="text-align:center;font-size:1.2rem;margin-bottom:1rem;">Password Reset</h2>
      <p style="color:#aaa;font-size:.9rem;line-height:1.6;text-align:center;">Your password reset code is below. It expires in 15 minutes.</p>
      <div style="background:#ff9000;color:#000;font-size:1.8rem;font-weight:900;text-align:center;padding:.8rem;border-radius:6px;letter-spacing:.3em;margin:1.5rem 0;">
        {code}
      </div>
      <p style="color:#666;font-size:.75rem;text-align:center;">If you didn't request a reset, ignore this email — your password is safe.</p>
      <div style="text-align:center;margin-top:1.5rem;color:#333;font-size:.7rem;">&copy; 2026 AbyssHub</div>
    </div>
    '''
    await _send_mailgun(to_email, 'AbyssHub — Password Reset Code', html)

async def _send_mailgun(to: str, subject: str, html: str):
    url = f'https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages'
    try:
        auth = aiohttp.BasicAuth('api', MAILGUN_API_KEY)
        async with aiohttp.ClientSession(auth=auth) as session:
            async with session.post(url, data={
                'from': MAILGUN_FROM,
                'to': to,
                'subject': subject,
                'html': html,
            }) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.error(f'Mailgun error ({resp.status}): {body}')
                else:
                    logger.info(f'Email sent to {to}: {subject}')
    except Exception as e:
        logger.error(f'Mailgun send failed: {e}')
