from typing import Optional
import os
import discord
from datetime import datetime
from discord.enums import ChannelType
from discord.utils import get
import traceback
from utils.crypto_api import createOrder
from utils.db_functions import insertOrder
from utils.product_manager import linesInFile
import asyncio
from utils.cardpayment_utils import createPayment
import re
from discord_webhook import DiscordWebhook, DiscordEmbed


class PaymentModal(discord.ui.Modal, title='Payment Details'):
    def __init__(self, *, timeout=None, custom_id=None, test=None, productInfo):
        super().__init__(timeout=timeout, custom_id=custom_id)
        self.paymentType=test
        self.productInfo = productInfo
        self.pth = productInfo['product_file']
        current_stock = linesInFile(self.pth)
        self.quantity = discord.ui.TextInput(
            label=f'Quantity (Stock: {current_stock})',
            placeholder=f'Minimum: {productInfo["min_order_amount"]}'
        )
        self.email = discord.ui.TextInput(
            label='Email',
            placeholder='Enter email for delivery'
        )
        self.add_item(self.quantity)
        self.add_item(self.email)

    async def on_submit(self, interaction: discord.Interaction):
        if(int(self.quantity.value) < self.productInfo['min_order_amount']):
            embed = discord.Embed(title="Below Minimum Quantity", description=f"Please enter a quantity greater than or equal to {self.productInfo['min_order_amount']}.",
                    colour=0xde2a2a,
                    timestamp=datetime.now())
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        totalStock = linesInFile(self.productInfo['product_file'])
        if(int(self.quantity.value) > totalStock):
            embed = discord.Embed(title="Quantity Above Stock Amount", description=f"Most you can purchase right now is {totalStock}",
                    colour=0xde2a2a,
                    timestamp=datetime.now())


            return await interaction.response.send_message(embed=embed, ephemeral=True)
        if(re.findall(r"[a-z0-9]+@[a-z]+\.[a-z]+", self.email.value) == []):
            embed = discord.Embed(title="Invalid Email", description="Please enter a valid email.",
                    colour=0xde2a2a,
                    timestamp=datetime.now())

            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if(self.paymentType == "Crypto"):
            if(orderDetails := createOrder(self.productInfo['price'], int(self.quantity.value), self.email.value, self.productInfo['name'])):
                insertOrder(orderDetails['id'], orderDetails['metadata']['orderId'], orderDetails['amount'], orderDetails['checkoutLink'], orderDetails['status'], orderDetails['expirationTime'], orderDetails['metadata']['itemDesc'], orderDetails['metadata']['buyerEmail'], orderDetails['metadata']['orderQuantity'], interaction.user.id, self.paymentType.lower())
                embed = discord.Embed(title="ANY.XYZ Order",
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
                                value=f"```${orderDetails['amount']} ({orderDetails['metadata']['orderQuantity']} @ ${orderDetails['metadata']['pricePer']} Each)```",
                                inline=False)
                embed.add_field(name="Payment Expiration",
                                value=f"<t:{orderDetails['expirationTime']}:R>",
                                inline=False)
                embed.add_field(name="Payment Link",
                                value=orderDetails['checkoutLink'],
                                inline=False)

                await interaction.response.send_message(embed=embed, ephemeral=True)
                try:
                    await interaction.user.send(embed=embed)
                except:
                    pass

                webhook = DiscordWebhook(url=os.environ.get('ORDER_WEBHOOK_URL', 'https://discordapp.com/api/webhooks/1391143167738249379/Hd0UQZzUMzPYiqkp4xsbNzJsyZa78mYFya2CgEBLaQjmrxn0ZIHD9OG8JqmUvWZqtm6W'), username="ANY.XYZ Orders")

                embed = DiscordEmbed(title="New Invoice Created", color="03b2f8")
                embed.set_footer(text="ANY.XYZ Store Notifications")
                embed.set_timestamp()
                embed.add_embed_field(name="Order ID", value=orderDetails['metadata']['orderId'], inline=False)
                embed.add_embed_field(name="Quantity", value=orderDetails['metadata']['orderQuantity'], inline=False)
                embed.add_embed_field(name="Amount", value=f"${orderDetails['amount']} ({orderDetails['metadata']['orderQuantity']} @ ${orderDetails['metadata']['pricePer']} Each)", inline=False)
                embed.add_embed_field(name="Method", value="Crypto", inline=False)
                embed.add_embed_field(name="User", value=f"<@{interaction.user.id}>", inline=False)

                webhook.add_embed(embed)
                response = webhook.execute()
        elif(self.paymentType == "CreditCard"):
            plink, url = createPayment(int(self.quantity.value), self.productInfo['stripe_priceident'])
            import uuid, time
            #original_id, order_id, amount, checkoutLink, status, expirationTime, item, buyeremail, quantity, discordid, method
            orderId = str(uuid.uuid4())
            cost = self.productInfo['price']*int(self.quantity.value)
            insertOrder(plink, orderId, cost, url, "New", int(time.time())+3600, f"x({self.quantity.value}) {self.productInfo['name']}", self.email.value, self.quantity.value, interaction.user.id, self.paymentType.lower())
            embed = discord.Embed(title="ANY.XYZ Order",
                    url=url,
                    colour=0x7a00f5,
                    timestamp=datetime.now())

            embed.add_field(name="Order ID",
                            value=f'```{orderId} ({plink.split("_")[1]})```',
                            inline=False)
            embed.add_field(name="Product",
                            value=f"```{self.productInfo['name']}```",
                            inline=False)
            embed.add_field(name="Quantity",
                            value=f"```{int(self.quantity.value)}```",
                            inline=False)
            embed.add_field(name="Amount",
                            value=f"```${cost} ({int(self.quantity.value)} @ ${self.productInfo['price']} Each)```",
                            inline=False)
            embed.add_field(name="Payment Link",
                            value=url,
                            inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)
            try:
                await interaction.user.send(embed=embed)
            except:
                pass
            
            webhook = DiscordWebhook(url=os.environ.get('ORDER_WEBHOOK_URL', 'https://discordapp.com/api/webhooks/1391143167738249379/Hd0UQZzUMzPYiqkp4xsbNzJsyZa78mYFya2CgEBLaQjmrxn0ZIHD9OG8JqmUvWZqtm6W'), username="ANY.XYZ Orders")

            embed = DiscordEmbed(title="New Invoice Created", color="03b2f8")
            embed.set_footer(text="ANY.XYZ Store Notifications")
            embed.set_timestamp()
            embed.add_embed_field(name="Order ID", value=f'{orderId} ({plink.split("_")[1]})', inline=False)
            embed.add_embed_field(name="Quantity", value=f"{int(self.quantity.value)}", inline=False)
            embed.add_embed_field(name="Amount", value=f"${cost} ({int(self.quantity.value)} @ ${self.productInfo['price']} Each)", inline=False)
            embed.add_embed_field(name="Method", value="Stripe", inline=False)
            embed.add_embed_field(name="User", value=f"<@{interaction.user.id}>", inline=False)

            webhook.add_embed(embed)
            response = webhook.execute()
                        

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)

        traceback.print_exception(type(error), error, error.__traceback__)