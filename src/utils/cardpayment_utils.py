import os
import stripe


stripe.api_key = os.environ.get('STRIPE_API_KEY', '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')

def createPayment(quantity, price):
    payment = stripe.PaymentLink.create(
        line_items=[{"price": price, "quantity": int(quantity)}],
        invoice_creation={"enabled": True}
    )
    if(payment.active):
        return payment.id, payment.url
    return False
    
def get10LastInvoices():
    return stripe.checkout.Session.list(limit=10)

def getInvoiceById(invoiceId):
    return stripe.Invoice.retrieve(invoiceId)