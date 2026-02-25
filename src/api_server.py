import json
from aiohttp import web
from loguru import logger


async def start_api_server(secret: str, port: int = 8080):
    """
    Lightweight HTTP API server that runs alongside the Discord bot.
    Allows pushing a new products.json without a redeploy.
    """
    app = web.Application()

    async def health(request):
        return web.json_response({'status': 'ok'})

    async def update_products(request):
        # Token auth
        auth = request.headers.get('Authorization', '')
        if auth != f"Bearer {secret}":
            logger.warning("Unauthorized attempt to update products via API")
            return web.Response(status=401, text="Unauthorized")

        try:
            new_data = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON body")

        if not isinstance(new_data, list):
            return web.Response(status=422, text="Expected a JSON array of products")

        # Preserve existing message_ids so the embed updater still knows which
        # message to edit — never let a push from VS Code wipe them.
        try:
            with open('products.json', 'r', encoding='utf-8') as f:
                existing = json.load(f)
            existing_ids = {p['name']: p.get('message_id', 0) for p in existing}
            for p in new_data:
                p['message_id'] = existing_ids.get(p['name'], 0)
        except Exception:
            pass  # File didn't exist yet — that's fine

        with open('products.json', 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)

        logger.success(f"products.json updated via API push ({len(new_data)} products)")
        return web.json_response({'status': 'ok', 'products': len(new_data)})

    app.router.add_get('/health', health)
    app.router.add_put('/api/products', update_products)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"API server listening on :{port}")
