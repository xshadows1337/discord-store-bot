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
from utils.db_functions import getOrdersByDiscordId

class InvoicesCommand:
    
    def __init__(self, client, tree, config) -> None:
        @tree.command(guild = discord.Object(id=config['discord_guild_id']), name = 'invoices', description='Fetch all your invoices')
        async def invoice(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)
            userInvoices = getOrdersByDiscordId(interaction.user.id)
            
            embed = discord.Embed(title="Invoice List",
                    colour=0x4900f5,
                    timestamp=datetime.now())

            invoices = []
            for invoice in userInvoices:
                invoices.append(f"- {invoice[2]} (${invoice[3]} - {invoice[5]}) ")

            formattedInvoices = "\n".join(invoices)

            embed.add_field(name="User",
                            value=f"<@{interaction.user.id}>",
                            inline=False)
            embed.add_field(name="Invoices",
                            value=f"```{formattedInvoices}```",
                            inline=False)
            await interaction.edit_original_response(embed=embed)