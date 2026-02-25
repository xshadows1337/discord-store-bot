from typing import Optional
import discord
from discord import app_commands
from datetime import datetime
from setuptools import Command
import asyncio
from discord.ext.commands import cooldown, BucketType
from datetime import timedelta
import math
import time
from readsettings import ReadSettings
from utils.product_manager import getAccounts, linesInFile
from utils.db_functions import getOrderById

class InvoiceCommand:
    
    def __init__(self, client, tree, config) -> None:
        @tree.command(guild = discord.Object(id=config['discord_guild_id']), name = 'invoice', description='Fetch an invoice by ID')
        async def invoice(interaction: discord.Interaction, invoice: str):
            await interaction.response.defer(ephemeral=True, thinking=True)
            invoice = getOrderById(invoice)
            if(invoice == None):
                embed = discord.Embed(title="Error: Invoice Not Found", color=0xff0000)
                await interaction.edit_original_response(embed=embed)
                return
            
            if(invoice[10] != interaction.user.id):
                if(interaction.user.id not in config['admin_ids']):
                    embed = discord.Embed(title="Error", description="You are not an admin.", color=0xff0000)
                    await interaction.edit_original_response(embed=embed)
                    return
            if(invoice[5] == 'New'):
                checkoutLink = invoice[4]
                
                products = ReadSettings('products.json')
                productName = ' '.join(invoice[7].split(' ')[1:])
                for prod in products.json():
                    if(prod['name'] in productName):
                        product = prod
                embed = discord.Embed(title="ANY.XYZ Order",
                    url=checkoutLink,
                    colour=0x7a00f5,
                    timestamp=datetime.now())
                

                embed.add_field(name="Order ID",
                                value=f"```{invoice[2]}```",
                                inline=False)
                embed.add_field(name="Product",
                                value=f"```{invoice[7]}```",
                                inline=False)
                embed.add_field(name="Quantity",
                                value=f"```{invoice[8]}```",
                                inline=False)
                embed.add_field(name="Amount",
                                value=f"```${invoice[3]} ({invoice[8]} @ ${product['price']})```",
                                inline=False)
                embed.add_field(name="Payment Expiration",
                                value=f"<t:{invoice[6]}:R>",
                                inline=False)
                embed.add_field(name="Status",
                                value=f"```{invoice[5]}```",
                                inline=False)
                embed.add_field(name="Payment Link",
                                value=checkoutLink,
                                inline=False)

                await interaction.edit_original_response(embed=embed)
            elif(invoice[5] == 'Settled'):
                checkoutLink = invoice[4]
                products = ReadSettings('products.json')
                productName = ' '.join(invoice[7].split(' ')[1:])
                for prod in products.json():
                    if(prod['name'] in productName):
                        product = prod
                embed = discord.Embed(title="ANY.XYZ Order",
                    url=checkoutLink,
                    colour=0x7a00f5,
                    timestamp=datetime.now())
                

                embed.add_field(name="Order ID",
                                value=f"```{invoice[2]}```",
                                inline=False)
                embed.add_field(name="Product",
                                value=f"```{invoice[7]}```",
                                inline=False)
                embed.add_field(name="Quantity",
                                value=f"```{invoice[8]}```",
                                inline=False)
                embed.add_field(name="Amount",
                                value=f"```${invoice[3]} ({invoice[8]} @ ${product['price']})```",
                                inline=False)
                embed.add_field(name="Payment Expiration",
                                value=f"<t:{invoice[6]}:R>",
                                inline=False)
                embed.add_field(name="Status",
                                value=f"```{invoice[5]}```",
                                inline=False)
                embed.add_field(name="Payment Link",
                                value=checkoutLink,
                                inline=False)

                deliveryFIle = f"delivered_orders/{invoice[2]}.txt"
                try:
                    await client.get_user(invoice[10]).send(file=discord.File(deliveryFIle))
                except Exception as e:
                    print(f'Failed to DM User {e}')
                    pass
                try:
                    await interaction.edit_original_response(embed=embed, attachments=[discord.File(deliveryFIle)])
                except FileNotFoundError as e:
                    embed = discord.Embed(title="Error: Delivery File Not Found!", color=0xff0000)
                    await interaction.edit_original_response(embed=embed)
                    return
            #print(test)