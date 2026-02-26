import os
import sqlite3
import requests
import uuid
from datetime import datetime, timedelta
from pathlib import Path

_ORDERS_DB = str(Path(os.environ.get('DATA_DIR', Path(__file__).parent.parent)) / 'orders.db')

# ── NOWPayments configuration ─────────────────────────────────────────────────
NOWPAYMENTS_API_KEY = os.environ.get('NOWPAYMENTS_API_KEY', '')
NOWPAYMENTS_API_URL = 'https://api.nowpayments.io/v1'

# Map NOWPayments statuses → internal statuses used by the bot
_STATUS_MAP = {
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


def _headers():
    return {'x-api-key': NOWPAYMENTS_API_KEY}


def getOrderById(invoice_id):
    """
    Fetch NOWPayments invoice status and return a BTCPay-compatible dict
    so the rest of the codebase (main.py, payment_modal.py) doesn't change.
    Extra metadata is pulled from the local DB since NOWPayments doesn't
    store arbitrary metadata.
    """
    resp = requests.get(f"{NOWPAYMENTS_API_URL}/invoice/{invoice_id}", headers=_headers())
    if resp.status_code != 200:
        print(f"NOWPayments getOrderById error {resp.status_code}: {resp.text}")
        return False

    data = resp.json()
    mapped_status = _STATUS_MAP.get(data.get('status', 'waiting'), 'New')

    # Pull the stored metadata from the local DB
    local_row = {}
    try:
        conn = sqlite3.connect(_ORDERS_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE originalid = ?", (str(invoice_id),))
        row = cursor.fetchone()
        conn.close()
        if row:
            local_row = {
                'orderid':      row[2],
                'amount':       row[3],
                'checkoutlink': row[4],
                'expirationtime': row[6],
                'item':         row[7],
                'quantity':     row[8],
                'buyeremail':   row[9],
            }
    except Exception as e:
        print(f"DB lookup error in getOrderById: {e}")

    return {
        'id':           str(invoice_id),
        'status':       mapped_status,
        'checkoutLink': local_row.get('checkoutlink') or data.get('invoice_url', ''),
        'amount':       local_row.get('amount') or str(data.get('price_amount', '0')),
        'expirationTime': local_row.get('expirationtime', 0),
        'metadata': {
            'orderId':       local_row.get('orderid', str(invoice_id)),
            'itemDesc':      local_row.get('item', data.get('order_description', '')),
            'orderQuantity': str(local_row.get('quantity', 1)),
            'buyerEmail':    local_row.get('buyeremail', ''),
            'pricePer':      '0.00',
        },
    }


def createOrder(cost, quantity, email, product):
    """
    Create a NOWPayments hosted invoice and return a BTCPay-compatible dict.
    Fields: id, checkoutLink, status, amount, expirationTime, metadata.
    """
    if not NOWPAYMENTS_API_KEY:
        print("ERROR: NOWPAYMENTS_API_KEY environment variable is not set.")
        return False

    orderID = str(uuid.uuid4())
    total   = round(float(cost) * float(quantity), 2)
    expiry_unix = int((datetime.now() + timedelta(minutes=90)).timestamp())

    payload = {
        'price_amount':     total,
        'price_currency':   'usd',
        'order_id':         orderID,
        'order_description': f'x{quantity} {product}',
        'ipn_callback_url': 'https://xshadows.shop/api/nowpayments/ipn',
        'success_url':      'https://xshadows.shop/?payment=success',
        'cancel_url':       'https://xshadows.shop/?payment=cancel',
        'is_fixed_rate':    False,
        'is_fee_paid_by_user': False,
    }

    resp = requests.post(
        f"{NOWPAYMENTS_API_URL}/invoice",
        headers=_headers(),
        json=payload,
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        return {
            'id':           str(data['id']),
            'checkoutLink': data.get('invoice_url', ''),
            'status':       'New',
            'amount':       '{:.2f}'.format(total),
            'expirationTime': expiry_unix,
            'metadata': {
                'orderId':       orderID,
                'itemDesc':      f'x{quantity} {product}',
                'orderQuantity': str(quantity),
                'buyerEmail':    email,
                'pricePer':      '{:.2f}'.format(float(cost)),
            },
        }
    else:
        print(f"NOWPayments createOrder error {resp.status_code}: {resp.text}")
        return False


def sendProductToCustomer(email, orderId, product):
    """
    Email delivery placeholder — NOWPayments has no built-in email API.
    Product delivery is handled via Discord DM (see main.py).
    To enable emails, configure an SMTP provider here.
    """
    print(f"[sendProductToCustomer] Order {orderId} for {email} — Discord DM is primary delivery.")
    return

    # --- Legacy BTCPay HTML email (kept for reference, never reached) ---
    payload = {
    "email": email,
    "subject": "Order Delivery",
    "body": f"""
    <br><!-- Header -->
    <table width="100%" border="0" cellpadding="0" cellspacing="0" align="center" style="width:100%; margin:0 auto;">
        <tbody>
            <tr>
                <td height="20" style="height:20px;"></td>
            </tr>
            <tr>
                <td>
                    <table width="750" border="0" cellpadding="0" cellspacing="0" align="center"
                        style="max-width:750px; width:100%; margin:0 auto; background-color:#212121; border-radius:10px 10px 0 0;">
                        <tbody>
                            <tr>
                                <td height="40" style="height:40px;"></td>
                            </tr>
                            <tr>
                                <td>
                                    <table width="540" border="0" cellpadding="0" cellspacing="0" align="center"
                                        style="max-width:690px; width:100%; margin:0 auto;">
                                        <tbody>
                                            <tr>
                                                <td>
                                                    <!-- Left Column -->
                                                    <table width="260" border="0" cellpadding="0" cellspacing="0"
                                                        align="left"
                                                        style="max-width:260px; width:100%; display:inline-block; vertical-align:top;">
                                                        <tbody>
                                                            <tr>
                                                                <td align="left">
                                                                    <h1
                                                                        style="margin:0; font-size:28px; color:#ffffff; font-family:'Open Sans', Arial, sans-serif;">
                                                                        ANY.XYZ</h1>
                                                                </td>
                                                            </tr>
                                                            <tr>
                                                                <td height="30" style="height:30px;"></td>
                                                            </tr>
                                                            <tr>
                                                                <td
                                                                    style="font-size:12px; color:#5b5b5b; font-family:'Open Sans', Arial, sans-serif; line-height:18px; vertical-align:top; text-align:left;">
                                                                    <br>
                                                                </td>
                                                            </tr>
                                                        </tbody>
                                                    </table>
                                                    <!-- Right Column -->
                                                    <table width="260" border="0" cellpadding="0" cellspacing="0"
                                                        align="right"
                                                        style="max-width:260px; width:100%; display:inline-block; vertical-align:top;">
                                                        <tbody>
                                                            <tr>
                                                                <td height="20" style="height:20px;"></td>
                                                            </tr>
                                                            <tr>
                                                                <td height="5" style="height:5px;"></td>
                                                            </tr>
                                                            <tr>
                                                                <td
                                                                    style="font-size:21px; letter-spacing:-1px; font-family:'Open Sans', Arial, sans-serif; line-height:1; vertical-align:top; text-align:right;">
                                                                    <h4 style="margin:0; font-size:21px; color:#9c00ff;">
                                                                        Product Delivery</h4>
                                                                </td>
                                                            </tr>
                                                            <tr>
                                                                <td height="20" style="height:20px;"></td>
                                                            </tr>
                                                            <tr>
                                                                <td
                                                                    style="line-height:18px; vertical-align:top; text-align:right; font-family:'Open Sans', Arial, sans-serif; font-size:12px;">
                                                                    <small style="color:#ffffff;">ORDER</small>
                                                                    <span style="font-size:12px; color:#9c00ff;">
                                                                        #{orderId}</span>
                                                                    <br>
                                                                </td>
                                                            </tr>
                                                        </tbody>
                                                    </table>
                                                </td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </td>
            </tr>
        </tbody>
    </table>
    <!-- /Header -->

    <!-- Billing and Shipping Info Spacer -->
    <table width="100%" border="0" cellpadding="0" cellspacing="0" align="center" style="width:100%; margin:0 auto;">
        <tbody>
            <tr>
                <td>
                    <table width="750" border="0" cellpadding="0" cellspacing="0" align="center"
                        style="max-width:750px; width:100%; margin:0 auto; background-color:#212121;">
                        <tbody>
                            <tr>
                                <td height="30" style="height:30px;"></td>
                            </tr>
                            <tr>
                                <td><br></td>
                            </tr>
                        </tbody>
                    </table>
                </td>
            </tr>
        </tbody>
    </table>

    <!-- Order Details -->

    <!-- /Order Details -->
    <table width="100%" border="0" cellpadding="0" cellspacing="0" align="center" style="width:100%; margin:0 auto;">
        <tr>
            <td>
                <table width="750" border="0" cellpadding="0" cellspacing="0" align="center"
                    style="max-width:750px; width:100%; margin:0 auto; background-color:#212121;">
                    <tr>
                        <td style="padding:20px;">
                            <p
                                style="font-family:'Open Sans', Arial, sans-serif; font-size:14px; color:#ffffff; margin:0 0 10px 0;">
                                Your License Key(s):</p>
                            <div style="overflow-y:auto; max-height:300px; background-color:#ffffff; color:#000000; padding:10px; display: inline-block; max-width: 685px; min-width: 685px; overflow:auto; font-family:'Courier New', monospace; font-size:12px; line-height:1.5; border:1px solid #cccccc; white-space:pre-wrap;">{product}</div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
    <!-- /Total Section -->

    <!-- Footer -->
    <table width="100%" border="0" cellpadding="0" cellspacing="0" align="center" style="width:100%; margin:0 auto;">
        <tbody>
            <tr>
                <td>
                    <table width="750" border="0" cellpadding="0" cellspacing="0" align="center"
                        style="max-width:750px; width:100%; margin:0 auto; background-color:#212121; border-radius:0 0 10px 10px;">
                        <tbody>
                            <tr>
                                <td>
                                    <table width="640" border="0" cellpadding="0" cellspacing="0" align="center"
                                        style="max-width:690px; width:100%; margin:0 auto;">
                                        <tbody>
                                            <tr>
                                                <td align="left"
                                                    style="font-size:12px; font-family:'Open Sans', Arial, sans-serif; line-height:18px; vertical-align:top; text-align:left; color:#ffffff;">
                                                    Thanks for shopping at ANY.XYZ!<br><br>
                                                    Best Regards,<br>
                                                    ANY.XYZ Team.<br><br>
                                                    Discord: <a href="https://discord.gg/BuAcvyVmsE"
                                                        style="color:#9c00ff; text-decoration:none;">https://discord.gg/BuAcvyVmsE</a>
                                                </td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </td>
                            </tr>
                            <tr>
                                <td height="50" style="height:50px;"></td>
                            </tr>
                        </tbody>
                    </table>
                </td>
            </tr>
            <tr>
                <td height="20" style="height:20px;"></td>
            </tr>
        </tbody>
    </table>
    <!-- /Footer -->
    """
    }
    # (unreachable — kept for reference only)
