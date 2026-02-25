import sqlite3
from .crypto_api import getOrderById

def insertOrder(original_id, order_id, amount, checkoutLink, status, expirationTime, item, buyeremail, quantity, discordid, method):
    conn = sqlite3.connect('orders.db')
    
    try:
        cursor = conn.cursor()
        
        query = """
        INSERT INTO orders (originalid, orderid, amount, checkoutlink, status, expirationtime, item, quantity, buyeremail, discordid, method) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        cursor.execute(query, (original_id, order_id, str(amount), checkoutLink, status, int(expirationTime), item, int(quantity), buyeremail, int(discordid), str(method)))
        
        conn.commit()
        print("Order inserted successfully.")
    
    except sqlite3.Error as e:
        print("An error occurred while inserting the order:", e)
    
    finally:
        conn.close()
    
    
def getOrdersByDiscordId(discordid):
    conn = sqlite3.connect('orders.db')
    
    try:
        cursor = conn.cursor()
        
        query = """
        SELECT * FROM orders WHERE discordid = ?
        """
        
        cursor.execute(query, (discordid,))
        
        orders = cursor.fetchall()
        
        return orders
    
    except sqlite3.Error as e:
        print("An error occurred while retrieving orders by Discord ID:", e)
    
    finally:
        conn.close()
        
#getOrdersByDiscordId(299195277187743744)

def getAllNewOrders():
    conn = sqlite3.connect('orders.db')
    try:
        cursor = conn.cursor()
        
        query = """
        SELECT * FROM orders WHERE status = 'New' OR status = 'Processing'
        """
        
        cursor.execute(query)
        
        orders = cursor.fetchall()
        return orders
    
    except sqlite3.Error as e:
        print("An error occurred while retrieving new orders:", e)
    
    finally:
        conn.close()
        
def getOutOfStockOrders():
    conn = sqlite3.connect('orders.db')
    try:
        cursor = conn.cursor()
        
        query = """
        SELECT * FROM orders WHERE status = 'OOS'
        """
        
        cursor.execute(query)
        
        orders = cursor.fetchall()
        return orders
    
    except sqlite3.Error as e:
        print("An error occurred while retrieving new orders:", e)
    
    finally:
        conn.close()
        
def setOrderStatusById(originalid, status):
    conn = sqlite3.connect('orders.db')
    
    try:
        cursor = conn.cursor()
        
        query = """
        UPDATE orders SET status =? WHERE originalid = ?
        """
        
        cursor.execute(query, (status, originalid))
        
        conn.commit()
        return True
    
    except sqlite3.Error as e:
        print("An error occurred while updating the order status:", e)
    
    finally:
        conn.close()
        
        
def getOrderById(order_id):
    conn = sqlite3.connect('orders.db')
    
    try:
        cursor = conn.cursor()
        
        query = """
        SELECT * FROM orders WHERE orderid = ?
        """
        
        cursor.execute(query, (order_id,))
        
        order = cursor.fetchone()
        
        return order
    
    except sqlite3.Error as e:
        print("An error occurred while retrieving the order by ID:", e)
    
    finally:
        conn.close()