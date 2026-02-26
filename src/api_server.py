import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path
import aiohttp
from aiohttp import web
from loguru import logger

NOWPAYMENTS_IPN_SECRET = os.environ.get('NOWPAYMENTS_IPN_SECRET', '')

# ── Live order events (in-memory ring buffer for toast notifications) ─────────
_events: list[dict] = []          # [{"id": int, "product": str}, …]
_event_counter: int = 0
_EVENTS_MAX = 100                  # keep last 100 events

# ── VPN / Proxy detection cache ───────────────────────────────────────────────
_vpn_cache: dict[str, tuple[bool, float]] = {}   # ip → (is_blocked, expiry)
_VPN_CACHE_TTL = 3600   # cache result for 1 hour
_PRIVATE_PREFIXES = ('10.', '172.', '192.168.', '127.', '::1', 'localhost')

async def _is_vpn(ip: str) -> bool:
    """VPN/proxy check — currently disabled."""
    return False

_VPN_BLOCK_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>AbyssHUB — Access Restricted</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#000;color:#fff;font-family:'Arial',sans-serif;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:2rem 1rem;}
  .logo{font-size:2rem;font-weight:900;letter-spacing:-1px;margin:2.5rem 0 2rem;}
  .logo .hub{background:#ff9000;color:#000;border-radius:4px;padding:2px 10px 3px;margin-left:3px;}
  .notice-box{max-width:620px;width:100%;text-align:left;}
  h1{font-size:1.4rem;font-weight:900;margin-bottom:1.5rem;text-align:center;letter-spacing:.02em;}
  .video-block{width:100%;max-width:380px;margin:0 auto 2rem;border:2px solid #333;border-radius:4px;overflow:hidden;background:#0a0a0a;display:flex;align-items:center;justify-content:center;height:180px;}
  .shield-icon{font-size:4rem;opacity:.25;}
  .btn-row{display:flex;flex-direction:column;gap:.75rem;align-items:center;margin-bottom:2rem;}
  .btn-notice{background:#ff9000;color:#000;border:2px solid #ff9000;border-radius:4px;padding:.7rem 2.5rem;font-size:.95rem;font-weight:900;cursor:default;letter-spacing:.03em;width:260px;text-align:center;}
  .btn-law{background:transparent;color:#fff;border:2px solid #ff9000;border-radius:4px;padding:.7rem 2.5rem;font-size:.95rem;font-weight:700;cursor:default;width:260px;text-align:center;}
  p{color:#ccc;font-size:.88rem;line-height:1.75;margin-bottom:1rem;}
  a{color:#ff9000;text-decoration:none;}
  .footer{margin-top:3rem;color:#333;font-size:.72rem;text-align:center;}
</style>
</head>
<body>
  <div class="logo">ABYSS<span class="hub">HUB</span></div>
  <div class="notice-box">
    <h1>ACCESS RESTRICTED — VPN DETECTED</h1>
    <div class="video-block"><div class="shield-icon">&#128683;</div></div>
    <div class="btn-row">
      <div class="btn-notice">Notice to Users</div>
      <div class="btn-law">Why Am I Blocked?</div>
    </div>
    <p>Dear user,</p>
    <p>We have detected that you are accessing AbyssHUB through a <strong>VPN, proxy, or anonymizing network</strong>. To protect the integrity of our platform and comply with fraud prevention requirements, we do not permit access from VPN or proxy connections.</p>
    <p>This restriction exists to prevent fraudulent purchases, chargebacks, and abuse of our automated delivery system. We take the security of our products and customers seriously.</p>
    <p>To access AbyssHUB, please <strong>disable your VPN or proxy</strong> and reload the page. If you believe this is an error, please <a href="https://discord.gg/Y69UbMUEfu" target="_blank">contact us on Discord</a>.</p>
    <p>We apologize for the inconvenience and appreciate your understanding.</p>
  </div>
  <div class="footer">&copy; 2026 AbyssHUB &mdash; All rights reserved.</div>
</body>
</html>
"""

# ── Security / DDoS mitigations ───────────────────────────────────────────────
# Per-IP sliding-window rate limits
_rate:      dict[str, list[float]] = {}   # ip → request timestamps (all routes)
_rate_co:   dict[str, list[float]] = {}   # ip → request timestamps (checkout only)
_error_hits: dict[str, int]        = {}   # ip → 4xx/5xx count
_banned:    dict[str, float]       = {}   # ip → ban expiry timestamp

# Thresholds
_GLOBAL_WINDOW   = 60;  _GLOBAL_MAX    = 120   # 120 req/min across all routes
_CO_WINDOW       = 60;  _CO_MAX        = 10    # 10 checkout req/min
_ERR_MAX         = 20    # 4xx errors before auto-ban
_BAN_DURATION    = 600   # 10-minute ban

# Paths that scanners/bots probe — instant 404 + count toward error ban
_SCANNER_PATHS = {
    '/.env', '/wp-admin', '/wp-login.php', '/phpmyadmin', '/admin',
    '/config.php', '/.git/config', '/xmlrpc.php', '/shell.php',
    '/backup.sql', '/db.sql', '/actuator', '/console', '/manager',
}

def _get_ip(request) -> str:
    return request.headers.get('X-Forwarded-For', request.remote or '0.0.0.0').split(',')[0].strip()

def _is_banned(ip: str) -> bool:
    expiry = _banned.get(ip)
    if expiry and time.time() < expiry:
        return True
    if expiry:
        del _banned[ip]
    return False

def _ban(ip: str, reason: str):
    _banned[ip] = time.time() + _BAN_DURATION
    logger.warning(f"[SECURITY] Banned {ip} for {_BAN_DURATION}s — {reason}")

def _sliding_window(store: dict, ip: str, window: int, limit: int) -> bool:
    """Returns True (= blocked) if IP exceeds limit within window seconds."""
    now    = time.time()
    cutoff = now - window
    store[ip] = [t for t in store.get(ip, []) if t > cutoff]
    if len(store[ip]) >= limit:
        return True
    store[ip].append(now)
    return False

def _record_error(ip: str):
    _error_hits[ip] = _error_hits.get(ip, 0) + 1
    if _error_hits[ip] >= _ERR_MAX:
        _ban(ip, f"{_ERR_MAX} error responses")

# Legacy helper kept for backwards compat with existing code
def _is_rate_limited(ip: str) -> bool:
    return _sliding_window(_rate_co, ip, _CO_WINDOW, _CO_MAX)

# ── Live visitors tracking (in-memory) ───────────────────────────────────────
_visitors: dict[str, float] = {}   # sid → last_ping_time
_VISITOR_TTL = 45  # seconds before a session is considered gone

def _prune_visitors():
    cutoff = time.time() - _VISITOR_TTL
    dead = [sid for sid, t in _visitors.items() if t < cutoff]
    for sid in dead:
        del _visitors[sid]

def _live_count() -> int:
    _prune_visitors()
    return max(len(_visitors), 1)   # always show at least 1 (current user)

# Resolve paths relative to this file so they work regardless of CWD
_HERE = Path(__file__).parent
_STATIC_DIR = _HERE / 'static'


async def start_api_server(secret: str, port: int = 8080):
    """
    Lightweight HTTP API server that runs alongside the Discord bot.
    Allows pushing a new products.json without a redeploy.
    Also serves the xshadows.shop website at /.
    """
    @web.middleware
    async def security_middleware(request, handler):
        ip   = _get_ip(request)
        path = request.path

        # 1. Banned IPs → immediate drop
        if _is_banned(ip):
            return web.Response(status=429, text="Banned.")

        # 2. Scanner/probe paths → 404 + error counter
        if path in _SCANNER_PATHS or path.startswith('/.') or path.endswith('.php'):
            _record_error(ip)
            return web.Response(status=404, text="Not found.")

        # 3. Global rate limit (all routes combined)
        if _sliding_window(_rate, ip, _GLOBAL_WINDOW, _GLOBAL_MAX):
            _ban(ip, "global rate limit exceeded")
            return web.Response(status=429, text="Too many requests.")

        response = await handler(request)

        # 4. Track error rates; auto-ban aggressive scanners
        if response.status >= 400:
            _record_error(ip)

        # 5. Security headers on every response
        response.headers.setdefault('X-Content-Type-Options',    'nosniff')
        response.headers.setdefault('X-Frame-Options',           'DENY')
        response.headers.setdefault('X-XSS-Protection',          '1; mode=block')
        response.headers.setdefault('Referrer-Policy',           'strict-origin-when-cross-origin')
        response.headers.setdefault('Content-Security-Policy',
            "default-src 'self' https:; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src * data:;")
        return response

    app = web.Application(
        client_max_size=64 * 1024,       # 64 KB max request body — blocks large payload attacks
        middlewares=[security_middleware],
    )

    # ── Website ──────────────────────────────────────────────────────────────

    async def index(request):
        """Serve the store landing page — VPN/proxy IPs get the block page."""
        ip = _get_ip(request)
        if await _is_vpn(ip):
            return web.Response(
                text=_VPN_BLOCK_PAGE,
                content_type='text/html',
                charset='utf-8',
                status=403,
                headers={'Cache-Control': 'no-store'},
            )
        index_file = _STATIC_DIR / 'index.html'
        if not index_file.exists():
            return web.Response(status=404, text="index.html not found")
        content = index_file.read_bytes()
        return web.Response(
            body=content,
            content_type='text/html',
            charset='utf-8',
            headers={'Cache-Control': 'no-store, no-cache, must-revalidate'},
        )

    async def public_products(request):
        """Return products.json publicly (no auth) for the website, with live stock counts."""
        def _build_product_list():
            """Synchronous work — runs in a thread so it never blocks the event loop."""
            products_path = _HERE / 'products.json'
            try:
                with open(products_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                return []
            safe = []
            for p in data:
                stock = None
                product_file = p.get('product_file', '')
                if product_file:
                    # Resolve relative to src/ directory so paths always work
                    pf_path = (_HERE / product_file) if not os.path.isabs(product_file) else Path(product_file)
                    try:
                        with open(pf_path, 'r', encoding='utf-8', errors='ignore') as pf:
                            lines = [l.strip() for l in pf if l.strip()]
                        stock = len(lines)
                    except Exception:
                        stock = 0
                safe.append({
                    'name':            p.get('name', ''),
                    'description':     p.get('description', ''),
                    'requirements':    p.get('requirements', ''),
                    'price':           p.get('price', 0),
                    'min_order_amount': p.get('min_order_amount', 1),
                    'payment_methods': p.get('payment_methods', []),
                    'thumbnail_url':   p.get('thumbnail_url', ''),
                    'stock':           stock,
                    'new':             p.get('new', False),
                })
            return safe

        try:
            safe = await asyncio.to_thread(_build_product_list)
            return web.json_response(safe)
        except Exception as exc:
            logger.error(f"Error serving public products: {exc}")
            return web.Response(status=500, text="Internal error")

    async def create_checkout(request):
        """Public endpoint for the website checkout — creates a Stripe or NOWPayments session."""
        ip = request.headers.get('X-Forwarded-For', request.remote or '').split(',')[0].strip()
        if _is_rate_limited(ip):
            return web.Response(status=429, text="Too many requests — please wait a moment.")

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        product_name = body.get('product')
        quantity     = int(body.get('quantity', 1))
        email        = body.get('email', '').strip()
        method       = body.get('method', 'CRYPTO').upper()

        if not product_name or not email:
            return web.Response(status=422, text="product and email are required")

        try:
            with open('products.json', 'r', encoding='utf-8') as f:
                products_data = json.load(f)
        except FileNotFoundError:
            return web.Response(status=503, text="Products unavailable")

        product = next((p for p in products_data if p['name'] == product_name), None)
        if not product:
            return web.Response(status=404, text="Product not found")

        if method not in product.get('payment_methods', []):
            return web.Response(status=422, text=f"Payment method {method} not available for this product")

        min_qty = product.get('min_order_amount', 1)
        if quantity < min_qty:
            return web.json_response({'error': f'Minimum order quantity is {min_qty}'}, status=422)

        try:
            import asyncio
            loop = asyncio.get_running_loop()
            if method == 'CRYPTO':
                from utils.crypto_api import createOrder
                order = await loop.run_in_executor(
                    None, lambda: createOrder(product['price'], quantity, email, product['name'])
                )
                if not order:
                    return web.Response(status=502, text="Failed to create crypto invoice")
                checkout_link = order.get('checkoutLink') or order.get('checkoutLinkWithCustomCSS')
                if not checkout_link:
                    logger.error(f"BTCPay response missing checkoutLink: {order}")
                    return web.Response(status=502, text="Failed to get payment link")
                return web.json_response({'redirect_url': checkout_link})

            elif method == 'CREDITCARD':
                from utils.cardpayment_utils import createPayment
                result = await loop.run_in_executor(
                    None, lambda: createPayment(quantity, product['stripe_priceident'])
                )
                if not result:
                    return web.Response(status=502, text="Failed to create payment link")
                _, url = result
                return web.json_response({'redirect_url': url})

            else:
                return web.Response(status=422, text="Unknown payment method")
        except Exception as exc:
            logger.error(f"Checkout error: {exc}")
            return web.Response(status=500, text="Internal error")

    # ── Visitors ─────────────────────────────────────────────────────────────

    async def visitors_ping(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        sid = body.get('sid') or str(uuid.uuid4())
        _visitors[sid] = time.time()
        return web.json_response({'sid': sid, 'count': _live_count()})

    async def visitors_leave(request):
        try:
            body = await request.json()
            sid = body.get('sid', '')
            _visitors.pop(sid, None)
        except Exception:
            pass
        return web.Response(status=204)

    # ── NOWPayments IPN ──────────────────────────────────────────────────────────

    async def nowpayments_ipn(request):
        """
        NOWPayments Instant Payment Notification handler.
        Receives payment status updates and syncs the local DB immediately.
        """
        body_bytes = await request.read()

        # Verify HMAC-SHA512 signature if IPN secret is configured
        if NOWPAYMENTS_IPN_SECRET:
            sig = request.headers.get('x-nowpayments-sig', '')
            expected = hmac.new(
                NOWPAYMENTS_IPN_SECRET.encode(),
                body_bytes,
                hashlib.sha512
            ).hexdigest()
            if not hmac.compare_digest(sig.lower(), expected.lower()):
                logger.warning("NOWPayments IPN: invalid signature")
                return web.Response(status=401, text="Invalid signature")

        try:
            data = json.loads(body_bytes)
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        invoice_id   = str(data.get('invoice_id') or data.get('order_id', ''))
        now_status   = data.get('payment_status', '')
        STATUS_MAP = {
            'waiting':        'New',
            'confirming':     'Processing',
            'confirmed':      'Processing',
            'sending':        'Processing',
            'finished':       'Settled',
            'failed':         'Expired',
            'refunded':       'Expired',
            'expired':        'Expired',
            'partially_paid': 'Expired',
        }
        internal_status = STATUS_MAP.get(now_status)
        if not internal_status:
            logger.info(f"NOWPayments IPN: unhandled status '{now_status}' for invoice {invoice_id}")
            return web.Response(status=200, text="OK")

        try:
            from utils.db_functions import setOrderStatusById
            setOrderStatusById(invoice_id, internal_status)
            logger.info(f"NOWPayments IPN: invoice {invoice_id} → {internal_status}")
        except Exception as exc:
            logger.error(f"NOWPayments IPN DB update failed: {exc}")

        # Push a live event for toast notifications on the storefront
        if internal_status == 'Settled':
            global _event_counter
            _event_counter += 1
            product_name = data.get('order_description') or data.get('product_id') or 'a product'
            _events.append({'id': _event_counter, 'product': str(product_name)})
            if len(_events) > _EVENTS_MAX:
                _events.pop(0)

        return web.Response(status=200, text="OK")

    # ── Events feed (live order toasts) ─────────────────────────────────────

    async def events_feed(request):
        """Return new order events since a given id for the storefront toast system."""
        try:
            since = int(request.rel_url.query.get('since', 0))
        except (ValueError, TypeError):
            since = 0
        new_events = [e for e in _events if e['id'] > since]
        return web.json_response(new_events)
    # ── VPN check endpoint (client-side secondary verification) ──────────────

    async def vpn_check(request):
        """Return whether the requesting IP is a VPN/proxy. Used by client-side JS."""
        ip = _get_ip(request)
        blocked = await _is_vpn(ip)
        return web.json_response({'blocked': blocked})
    # ── Bot API ───────────────────────────────────────────────────────────────

    async def health(request):
        return web.json_response({'status': 'ok'})

    async def update_products(request):
        # Token auth
        auth = request.headers.get('Authorization', '')
        if auth != f"Bearer {secret}":
            logger.warning("Unauthorized attempt to update products via API")
            return web.Response(status=401, text="Unauthorized")

        try:
            new_data = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON body")

        if not isinstance(new_data, list):
            return web.Response(status=422, text="Expected a JSON array of products")

        # Preserve existing message_ids so the embed updater still knows which
        # message to edit — never let a push from VS Code wipe them.
        try:
            with open('products.json', 'r', encoding='utf-8') as f:
                existing = json.load(f)
            existing_ids = {p['name']: p.get('message_id', 0) for p in existing}
            for p in new_data:
                p['message_id'] = existing_ids.get(p['name'], 0)
        except Exception:
            pass  # File didn't exist yet — that's fine

        with open('products.json', 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)

        logger.success(f"products.json updated via API push ({len(new_data)} products)")
        return web.json_response({'status': 'ok', 'products': len(new_data)})

    # Website routes
    app.router.add_get('/',                      index)
    app.router.add_get('/api/public/products',   public_products)
    app.router.add_post('/api/create-checkout',  create_checkout)

    # Static asset serving (CSS, JS, images if added later)
    if _STATIC_DIR.exists():
        app.router.add_static('/static/', path=str(_STATIC_DIR), name='static')

    # Visitors (live user counter)
    app.router.add_post('/api/visitors/ping',  visitors_ping)
    app.router.add_post('/api/visitors/leave', visitors_leave)

    # NOWPayments IPN
    app.router.add_post('/api/nowpayments/ipn', nowpayments_ipn)

    # Events feed
    app.router.add_get('/api/events/feed', events_feed)

    # VPN check
    app.router.add_get('/api/vpn-check', vpn_check)

    # ── Auth endpoints ──────────────────────────────────────────────────────

    async def auth_register(request):
        ip = _get_ip(request)
        if _sliding_window(_rate_co, ip, _CO_WINDOW, _CO_MAX):
            return web.Response(status=429, text='Too many requests.')
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON')
        username = (body.get('username') or '').strip()
        email    = (body.get('email') or '').strip()
        password = body.get('password') or ''
        confirm  = body.get('confirm') or ''
        if password != confirm:
            return web.json_response({'ok': False, 'msg': 'Passwords do not match.'}, status=422)
        from utils.auth import register_user, send_verification_email
        ok, msg, uid = register_user(username, email, password)
        if not ok:
            return web.json_response({'ok': False, 'msg': msg}, status=422)
        # Send verification email
        try:
            await send_verification_email(email, msg)  # msg is the verify code on success
        except Exception as e:
            logger.error(f'Failed to send verify email: {e}')
        return web.json_response({'ok': True, 'msg': 'Account created! Check your email for a verification code.'})

    async def auth_verify(request):
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON')
        email = (body.get('email') or '').strip()
        code  = (body.get('code') or '').strip()
        from utils.auth import verify_email
        ok, msg = verify_email(email, code)
        return web.json_response({'ok': ok, 'msg': msg}, status=200 if ok else 422)

    async def auth_login(request):
        ip = _get_ip(request)
        if _sliding_window(_rate_co, ip, _CO_WINDOW, _CO_MAX):
            return web.Response(status=429, text='Too many requests.')
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON')
        email    = (body.get('email') or '').strip()
        password = body.get('password') or ''
        from utils.auth import login_user
        ok, msg, token = login_user(email, password)
        if not ok:
            return web.json_response({'ok': False, 'msg': msg}, status=401)
        return web.json_response({'ok': True, 'username': msg, 'token': token})

    async def auth_forgot(request):
        ip = _get_ip(request)
        if _sliding_window(_rate_co, ip, _CO_WINDOW, _CO_MAX):
            return web.Response(status=429, text='Too many requests.')
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON')
        email = (body.get('email') or '').strip()
        from utils.auth import request_password_reset, send_reset_email
        ok, msg, code = request_password_reset(email)
        if code:
            try:
                await send_reset_email(email, code)
            except Exception as e:
                logger.error(f'Failed to send reset email: {e}')
        return web.json_response({'ok': True, 'msg': 'If that email exists, a reset code has been sent.'})

    async def auth_reset(request):
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON')
        email    = (body.get('email') or '').strip()
        code     = (body.get('code') or '').strip()
        password = body.get('password') or ''
        from utils.auth import reset_password
        ok, msg = reset_password(email, code, password)
        return web.json_response({'ok': ok, 'msg': msg}, status=200 if ok else 422)

    async def auth_me(request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return web.json_response({'ok': False}, status=401)
        from utils.auth import verify_token, get_user_by_id
        data = verify_token(auth_header[7:])
        if not data:
            return web.json_response({'ok': False}, status=401)
        user = get_user_by_id(data['uid'])
        if not user:
            return web.json_response({'ok': False}, status=401)
        return web.json_response({'ok': True, 'user': user})

    app.router.add_post('/api/auth/register', auth_register)
    app.router.add_post('/api/auth/verify',   auth_verify)
    app.router.add_post('/api/auth/login',    auth_login)
    app.router.add_post('/api/auth/forgot',   auth_forgot)
    app.router.add_post('/api/auth/reset',    auth_reset)
    app.router.add_get('/api/auth/me',        auth_me)

    # ── Live Support Relay ──────────────────────────────────────────────────

    async def support_open(request):
        ip = _get_ip(request)
        if _sliding_window(_rate_co, ip, _CO_WINDOW, _CO_MAX):
            return web.Response(status=429, text='Too many requests.')
        try:
            body = await request.json()
        except Exception:
            body = {}
        username = (body.get('username') or 'Guest').strip()[:20]
        from utils.support_relay import create_web_ticket
        ticket = await create_web_ticket(username)
        if not ticket:
            return web.json_response({'ok': False, 'msg': 'Could not create ticket. Try Discord.'}, status=503)
        return web.json_response({'ok': True, 'ticket_id': ticket.ticket_id})

    async def support_send(request):
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text='Invalid JSON')
        ticket_id = body.get('ticket_id', '')
        text = (body.get('text') or '').strip()[:1000]
        if not ticket_id or not text:
            return web.Response(status=422, text='ticket_id and text required')
        from utils.support_relay import send_user_message
        ok = await send_user_message(ticket_id, text)
        return web.json_response({'ok': ok})

    async def support_poll(request):
        ticket_id = request.rel_url.query.get('ticket_id', '')
        try:
            since = int(request.rel_url.query.get('since', 0))
        except (ValueError, TypeError):
            since = 0
        from utils.support_relay import poll_staff_messages
        msgs = poll_staff_messages(ticket_id, since)
        return web.json_response(msgs)

    async def support_close(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        ticket_id = body.get('ticket_id', '')
        from utils.support_relay import close_web_ticket
        await close_web_ticket(ticket_id)
        return web.json_response({'ok': True})

    app.router.add_post('/api/support/open',  support_open)
    app.router.add_post('/api/support/send',  support_send)
    app.router.add_get('/api/support/poll',   support_poll)
    app.router.add_post('/api/support/close', support_close)

    # Bot API routes
    app.router.add_get('/health',        health)
    app.router.add_put('/api/products',  update_products)

    runner = web.AppRunner(
        app,
        handle_signals=False,
        keepalive_timeout=30,   # close idle keep-alive connections after 30s (slow loris)
        shutdown_timeout=10,
    )
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port, reuse_port=True, backlog=256)
    await site.start()
    logger.info(f"API server listening on :{port} — website live at /")
