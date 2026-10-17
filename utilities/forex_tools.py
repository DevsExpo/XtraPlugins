# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".

import httpx
from typing import Dict, Any

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message


@Friday.register_on_cmd(
    ["forex", "curr", "currency", "exchange"],
    cmd_help={
        "help": "Convert global fiat currencies with real-time foreign exchange market rates.",
        "example": "forex 100 USD EUR\nforex 5000 INR USD\ncurrency 1 BTC USD",
    },
    requires_input=True,
)
async def forex_convert_cmd(c: Client, m: Message):
    tokens = m.user_input.strip().split()
    amount = 1.0
    from_curr = "USD"
    to_curr = "EUR"

    if len(tokens) == 3:
        try:
            amount = float(tokens[0])
            from_curr = tokens[1].upper()
            to_curr = tokens[2].upper()
        except ValueError:
            return await m.handle_message("⚠️ <b>Usage:</b> <code>.forex &lt;amount&gt; &lt;FROM&gt; &lt;TO&gt;</code>\nExample: <code>.forex 100 USD EUR</code>")
    elif len(tokens) == 2:
        from_curr = tokens[0].upper()
        to_curr = tokens[1].upper()
    else:
        return await m.handle_message("⚠️ <b>Usage:</b> <code>.forex &lt;amount&gt; &lt;FROM&gt; &lt;TO&gt;</code>\nExample: <code>.forex 100 USD EUR</code>")

    msg = await m.handle_message(f"💱 Fetching exchange rates for <b>{from_curr} ➔ {to_curr}</b>...")

    url = f"https://open.er-api.com/v6/latest/{from_curr}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return await msg.edit_msg(f"❌ Failed to fetch forex data for <code>{from_curr}</code>.")
            data = resp.json()

        rates = data.get("rates", {})
        if to_curr not in rates:
            return await msg.edit_msg(f"❌ Currency <code>{to_curr}</code> not supported or invalid code.")

        rate = rates[to_curr]
        converted = amount * rate
        last_update = (data.get("time_last_update_utc") or "")[:16]

        # Key benchmark rates
        popular = ["USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD"]
        quick_grid = []
        for p in popular:
            if p != from_curr and p in rates:
                quick_grid.append(f"• 1 {from_curr} = <code>{rates[p]:.3f} {p}</code>")

        report = (
            f"💱 <b>Forex Currency Conversion:</b>\n\n"
            f"💵 <b>{amount:,.2f} {from_curr}</b> = <b>{converted:,.2f} {to_curr}</b>\n"
            f"📊 <b>Exchange Rate:</b> <code>1 {from_curr} = {rate:.4f} {to_curr}</code>\n"
            f"🕒 <b>Updated:</b> <code>{last_update} UTC</code>\n\n"
            f"<b>Popular Benchmarks:</b>\n" + "\n".join(quick_grid[:5])
        )

        await msg.edit_msg(report)

    except Exception as e:
        await msg.edit_msg(f"❌ Currency error: <code>{e}</code>")
