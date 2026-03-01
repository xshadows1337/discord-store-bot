import asyncio
import os
import hashlib

# Load .env early so every module-level os.environ.get() call sees the values
try:
    from dotenv import load_dotenv
    from pathlib import Path
    _env = Path(__file__).parent / '.env'
    if _env.exists():
        load_dotenv(_env, override=False)
except ImportError:
    pass

import discord
from discord import app_commands
from readsettings import ReadSettings
from command_handler import CommandHander
import time
from datetime import datetime
from discord.ext import tasks
from commands.setup_channels.setup_channels_command import SetupCommand
from commands.setup_channels.views.purchase_button_view import StoreView, build_store_embed
from utils.crypto_api import getOrderById, sendProductToCustomer
from utils.db_functions import getAllNewOrders, setOrderStatusById, getOutOfStockOrders
from utils.product_manager import getAccounts, linesInFile
from utils.cardpayment_utils import get10LastInvoices, getInvoiceById
from utils.env_config import Config

from loguru import logger

logger.add("output.log")

commandHandler = None

config = Config()
products = ReadSettings('products.json')
lastStock = {}
lastContentHash = None


def _store_content_hash():
    """Hash products.json + every stock file so any edit triggers a rebuild."""
    h = hashlib.md5()
    try:
        with open('products.json', 'rb') as f:
            h.update(f.read())
    except Exception:
        pass
    try:
        for product in ReadSettings('products.json').json():
            try:
                with open(product['product_file'], 'rb') as f:
                    h.update(f.read())
            except Exception:
                pass
    except Exception:
        pass
    return h.hexdigest()

def sendOrderWebhook(orderid, quantity, amount, method, user):
    from discord_webhook import DiscordWebhook, DiscordEmbed

    webhook = DiscordWebhook(url=os.environ.get('ORDER_WEBHOOK_URL', 'https://discordapp.com/api/webhooks/1391143167738249379/Hd0UQZzUMzPYiqkp4xsbNzJsyZa78mYFya2CgEBLaQjmrxn0ZIHD9OG8JqmUvWZqtm6W'), username="ANY.XYZ Orders")

    embed = DiscordEmbed(title="Invoice Paid!", color="00ff00")
    embed.set_footer(text="ANY.XYZ Store Notifications")
    embed.set_timestamp()
    embed.add_embed_field(name="Order ID", value=orderid, inline=False)
    embed.add_embed_field(name="Quantity", value=quantity, inline=False)
    embed.add_embed_field(name="Amount", value=amount, inline=False)
    embed.add_embed_field(name="Method", value=method, inline=False)
    embed.add_embed_field(name="User", value=f"<@{user}>", inline=False)

    webhook.add_embed(embed)
    response = webhook.execute()

class aclient(discord.Client):
    def __init__(self):
        super().__init__(intents = discord.Intents.all())
        self.synced = False
        self.started = False

    async def on_ready(self):
        await self.wait_until_ready()
        if not self.synced:
            # Register the Discord client with the support relay module
            from utils.support_relay import set_discord_client
            set_discord_client(self)

            guild_id = config['discord_guild_id']
            guild_obj = discord.Object(id=guild_id)
            logger.info(f"Syncing commands to guild {guild_id}...")
            # Clear stale global commands
            tree.clear_commands(guild=None)
            await tree.sync()
            # Sync guild commands
            synced_commands = await tree.sync(guild=guild_obj)
            logger.info(f"Synced {len(synced_commands)} guild commands: {[c.name for c in synced_commands]}")
            self.synced = True
        print(f"Logged into bot account: {self.user}.")
        if not self.checkPendingPayments.is_running():
            self.checkPendingPayments.start()
        logger.success('All threads running.')

    async def on_member_remove(self, member: discord.Member):
        """Post a leave notification when someone leaves the server."""
        channel = self.get_channel(1476360273341321391)
        if channel is None:
            return
        embed = discord.Embed(
            color=0xED4245,
            timestamp=datetime.now(),
        )
        embed.set_author(
            name=f"{member} left the server",
            icon_url=member.display_avatar.url,
        )
        embed.description = (
            f"{member.mention} has left **{member.guild.name}**.\n"
            f"\u200b"
        )
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "Unknown", inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_footer(text=f"ID: {member.id}  \u2022  xShadows Shop")
        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send leave message: {e}")
        
    async def setup_hook(self) -> None:
        self.add_view(StoreView())
        # Register persistent ticket views so buttons survive restarts
        from commands.tickets.views.ticket_panel_view import TicketPanelView
        from commands.tickets.views.ticket_channel_view import TicketChannelView
        self.add_view(TicketPanelView())
        self.add_view(TicketChannelView())

    async def on_message(self, message: discord.Message):
        """Forward staff replies in web-ticket channels to the support relay."""
        if message.author.bot:
            return
        try:
            from utils.support_relay import get_ticket_by_channel, push_staff_message
            ticket = get_ticket_by_channel(message.channel.id)
            if ticket and not ticket.closed:
                push_staff_message(message.channel.id, message.author.display_name, message.content)
        except Exception:
            pass
        
    @tasks.loop(seconds=10.0, reconnect=True)
    @logger.catch(onerror=lambda _: logger.exception(_))
    async def checkPendingPayments(self):
        global lastContentHash
        try:
            products = ReadSettings('products.json')
            store_channel = client.get_channel(config['store_channel_id'])
            if store_channel is None:
                logger.warning(f"Store channel {config['store_channel_id']} not found in cache, skipping...")
                return

            # Rebuild the store embed whenever products.json or any stock file changes
            current_hash = _store_content_hash()
            if current_hash != lastContentHash:
                lastContentHash = current_hash
                message_id = None
                for product in products.json():
                    mid = product.get('message_id')
                    if mid and mid != 0:
                        message_id = mid
                        break

                if message_id:
                    try:
                        msg = store_channel.get_partial_message(message_id)
                        await msg.edit(embed=build_store_embed(), view=StoreView())
                        logger.info('Store embed auto-updated.')
                    except Exception as e:
                        logger.error(f'Failed to auto-update store embed: {e}')
        
            for order in (getOutOfStockOrders() or []):
                productName = ' '.join(order[7].split(' ')[1:])
                for prod in products.json():
                    if(prod['name'] == productName):
                        product = prod
                accountsForOrder = getAccounts(product['product_file'], int(order[8]))
                if(len(accountsForOrder) >= int(order[8])):
                    logger.info(f'Sending product for out of stock order {order[2]}')
                    deliveryFIle = f"delivered_orders/{order[2]}.txt"
                    with open(deliveryFIle, 'w') as file:
                        file.writelines(accountsForOrder)
                    try:
                        await client.get_user(order[10]).send(file=discord.File(deliveryFIle))
                    except Exception as e:
                        logger.error(f'Failed to DM User {e}')
                        pass
                    sendProductToCustomer(order[9], order[2], "".join(accountsForOrder))
                    logger.success(f'Order {order[2]} has been settled')
                    setOrderStatusById(order[1],'Settled')
            
            for order in (getAllNewOrders() or []):
                if(order[11] == 'crypto'):
                    orderDetails = await asyncio.to_thread(getOrderById, order[1])
                    if(orderDetails['status'] == "New"):
                        continue
                    else:
                        setOrderStatusById(orderDetails['id'],orderDetails['status'])
                        if(orderDetails['status'] == "Settled"):
                            logger.warning(f'Order {orderDetails["metadata"]["orderId"]} is being settled')
                            embed = discord.Embed(title="ANY.XYZ Order Completed",
                            url=orderDetails['checkoutLink'],
                            colour=0x7a00f5,
                            timestamp=datetime.now())

                            embed.add_field(name="Order ID",
                                            value=f"```{orderDetails['metadata']['orderId']}```",
                                            inline=False)
                            embed.add_field(name="Product",
                                            value=f"```{orderDetails['metadata']['itemDesc']}```",
                                            inline=False)
                            embed.add_field(name="Quantity",
                                            value=f"```{orderDetails['metadata']['orderQuantity']}```",
                                            inline=False)
                            embed.add_field(name="Amount",
                                            value=f"```${orderDetails['amount']}```",
                                            inline=False)
                            embed.add_field(name="Payment Expiration",
                                            value=f"<t:{orderDetails['expirationTime']}:R>",
                                            inline=False)
                            embed.add_field(name="Payment Link",
                                            value=orderDetails['checkoutLink'],
                                            inline=False)

                            try:
                                await client.get_user(order[10]).send(embed=embed)
                            except:
                                pass
                            productName = ' '.join(order[7].split(' ')[1:])
                            for prod in products.json():
                                if(prod['name'] == productName):
                                    product = prod
                            accountsForOrder = getAccounts(product['product_file'], int(orderDetails['metadata']['orderQuantity']))
                            if(len(accountsForOrder) == 0):
                                embed = discord.Embed(title="Out Of Stock", description="We are currenty out of stock for this product. Please wait for a restock.",
                                        colour=0xde2a2a,
                                        timestamp=datetime.now())

                                try:
                                    await client.get_user(order[10]).send(embed=embed)
                                except:
                                    pass
                                setOrderStatusById(order[1],'OOS')
                                sendProductToCustomer(order[9], order[2], "Ran out of stock while processing your order. Please contact the shop owner.")
                                return
                            
                            deliveryFIle = f"delivered_orders/{orderDetails['metadata']['orderId']}.txt"
                            with open(deliveryFIle, 'w') as file:
                                file.writelines(accountsForOrder)
                            try:
                                await client.get_user(order[10]).send(file=discord.File(deliveryFIle))
                            except Exception as e:
                                logger.error(f'Failed to DM User {e}')
                                pass
                            sendProductToCustomer(order[9], order[2], "".join(accountsForOrder))
                            logger.success(f'Order {orderDetails["metadata"]["orderId"]} has been settled')
                            asyncio.ensure_future(asyncio.to_thread(sendOrderWebhook, f'{orderDetails["metadata"]["orderId"]}', order[8], f"${order[3]} ({order[8]} @ ${product['price']} Each)", "Crypto", order[10]))
                elif(order[11] == "creditcard"):
                    invoices = await asyncio.to_thread(get10LastInvoices)
                    for invoice in invoices:
                        if(invoice['payment_link'] == order[1]):
                            if(invoice['payment_status'] == 'paid'):
                                try:
                                    receipt = (await asyncio.to_thread(getInvoiceById, invoice['invoice']))['hosted_invoice_url']
                                except:
                                    logger.error(f'Failed to get invoice. Invoice was none')
                                    continue
                                setOrderStatusById(order[1],'Settled')
                                logger.warning(f'Order {order[2]} is being settled')
                                embed = discord.Embed(title="ANY.XYZ Order Completed",
                                url=order[4],
                                colour=0x7a00f5,
                                timestamp=datetime.now())
                                orderId = order[2]
                                plink = order[1]
                                embed.add_field(name="Order ID",
                                                value=f'```{orderId} ({plink.split("_")[1]})```',
                                                inline=False)
                                embed.add_field(name="Product",
                                                value=f"```{order[7]}```",
                                                inline=False)
                                embed.add_field(name="Quantity",
                                                value=f"```{order[8]}```",
                                                inline=False)
                                embed.add_field(name="Amount",
                                                value=f"```${order[3]}```",
                                                inline=False)
                                embed.add_field(name="Receipt",
                                                value=receipt,
                                                inline=False)

                                try:
                                    await client.get_user(order[10]).send(embed=embed)
                                except:
                                    pass
                                productName = ' '.join(order[7].split(' ')[1:])
                                for prod in products.json():
                                    if(prod['name'] == productName):
                                        product = prod
                                accountsForOrder = getAccounts(product['product_file'], int(order[8]))
                                if(len(accountsForOrder) == 0):
                                    embed = discord.Embed(title="Out Of Stock", description="We are currenty out of stock for this product. Please wait for a restock.",
                                            colour=0xde2a2a,
                                            timestamp=datetime.now())

                                    try:
                                        await client.get_user(order[10]).send(embed=embed)
                                    except:
                                        pass
                                    setOrderStatusById(order[1],'OOS')
                                    sendProductToCustomer(order[9], order[2], "Ran out of stock while processing your order. Please contact the shop owner.")
                                    return
                                
                                deliveryFIle = f"delivered_orders/{order[2]}.txt"
                                with open(deliveryFIle, 'w') as file:
                                    file.writelines(accountsForOrder)
                                try:
                                    await client.get_user(order[10]).send(file=discord.File(deliveryFIle))
                                except Exception as e:
                                    print('Failed to DM User {e}')
                                    pass
                                sendProductToCustomer(order[9], order[2], "".join(accountsForOrder))
                                logger.success(f'Order {order[2]} has been settled')
                                asyncio.ensure_future(asyncio.to_thread(sendOrderWebhook, f'{orderId} ({plink.split("_")[1]})', order[8], f"${order[3]} ({order[8]} @ ${product['price']} Each)", "Stripe", order[10]))
                            else:
                                if(int(time.time() > order[6])):
                                    logger.info(f"Invoice {order[1]} has expired.")
                                    setOrderStatusById(order[1],'Expired')
        except Exception as e:
            logger.exception(e)
        
client = aclient()
tree = app_commands.CommandTree(client)
commandHandler = CommandHander(
    client, tree, config)

async def runner():
    global client, tree, commandHandler

    # Start the API server first so the website is up even if Discord 429s
    api_secret = os.environ.get('BOT_API_SECRET') or config.get('bot_api_secret', '')
    api_port = int(os.environ.get('PORT', 8080))
    if api_secret:
        from api_server import start_api_server
        await start_api_server(api_secret, api_port)
    else:
        logger.warning("BOT_API_SECRET not set — API server disabled")

    # Retry login with exponential backoff on 429.
    # Each retry creates a *fresh* Client so the old aiohttp session
    # is properly closed — no leaked sessions that compound the limit.
    delay = 30
    while True:
        try:
            await client.start(config['bot_token'])
            break
        except discord.HTTPException as e:
            if e.status == 429:
                # Use Discord's retry_after if provided, otherwise use our backoff
                wait = getattr(e, 'retry_after', None)
                if wait and isinstance(wait, (int, float)) and wait < 120:
                    wait = float(wait)
                else:
                    wait = float(delay)
                logger.warning(f"Login rate-limited (429). Closing client, retrying in {wait:.0f}s...")
                try:
                    await client.close()
                except Exception:
                    pass
                await asyncio.sleep(wait)
                delay = min(delay * 2, 60)  # cap at 60s
                # Rebuild with a fresh client to avoid stale session state
                client = aclient()
                tree = app_commands.CommandTree(client)
                commandHandler = CommandHander(client, tree, config)
            else:
                raise

asyncio.run(runner())