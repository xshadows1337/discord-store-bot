import discord
import threading
import math
from commands.setup_channels.setup_channels_command import SetupCommand
from commands.invoice.invoice_command import InvoiceCommand
from commands.invoices.invoices_command import InvoicesCommand
from commands.tickets.tickets_command import TicketsCommand

from datetime import datetime, timedelta

import asyncio

class CommandHander:
    def __init__(self, client, tree, config) -> None:
        self.client = client
        self.tree = tree
        self.config = config
        SetupCommand(self.client, self.tree, self.config)
        InvoiceCommand(self.client, self.tree, self.config)
        InvoicesCommand(self.client, self.tree, self.config)
        TicketsCommand(self.client, self.tree, self.config)
