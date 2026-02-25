import os
import requests, uuid
from datetime import datetime

BTCPAY_URL = os.environ.get('BTCPAY_URL', 'https://pay.xshadows.shop')
BTCPAY_STORE_ID = os.environ.get('BTCPAY_STORE_ID', 'BfNircsQUjse5CJ9wAyyUET5Q6muCVCqdvuZEqw99c32')
BTCPAY_API_TOKEN = os.environ.get('BTCPAY_API_TOKEN', '6979d4ba6006ce8d87d5ca2e0f04cc64c88899ba')
BTCPAY_EMAIL_TOKEN = os.environ.get('BTCPAY_EMAIL_TOKEN', '92f42e11da40e6ca9605d2e8a29e37ab5163a425')

def getOrderById(id):
    header = {'Authorization': f'token {BTCPAY_API_TOKEN}'}

    req = requests.get(f"{BTCPAY_URL}/api/v1/stores/{BTCPAY_STORE_ID}/invoices/{id}", headers=header)
    if(req.status_code == 200):
        return req.json()
    elif(req.status_code == 404):
        return False

def createOrder(cost, quantity, email, product):
    header = {'Authorization': f'token {BTCPAY_API_TOKEN}'}
    
    orderID = str(uuid.uuid4())
    payload = {
        "metadata": {
            "orderId": orderID,
            "itemDesc": f"x{quantity} {product}",
            "buyerEmail": email,
            "orderQuantity": str(quantity),
            "pricePer": "{:.2f}".format(float(cost)),
            "orderDate": datetime.now().now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        "checkout": {
            "speedPolicy": "MediumSpeed",
            "paymentMethods": [
            "BTC-CHAIN", "LTC-CHAIN"
            ],
            "defaultPaymentMethod": "BTC-CHAIN",
            "lazyPaymentMethods": True,
            "expirationMinutes": 90,
            "monitoringMinutes": 90,
            "paymentTolerance": 0,
        },
        "amount": "{:.2f}".format(float(float(cost) * float(quantity))),
        "currency": "USD",
        }
    

    req = requests.post(f"{BTCPAY_URL}/api/v1/stores/{BTCPAY_STORE_ID}/invoices", headers=header, json=payload)
    print(req.json())
    if req.status_code in (200, 201):
        return req.json()
    else:
        print(f"BTCPay error {req.status_code}: {req.text}")
        return False


def sendProductToCustomer(email, orderId, product):
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

    header = {'Authorization': f'token {BTCPAY_EMAIL_TOKEN}'}

    req = requests.post(f"{BTCPAY_URL}/api/v1/stores/{BTCPAY_STORE_ID}/email/send", json=payload, headers=header)