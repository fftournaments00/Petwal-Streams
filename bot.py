import os
import asyncio
import re
from telethon import TelegramClient, events
from aiohttp import web

# --- CONFIGURATION ---
API_ID = 34970400          
API_HASH = "b4d8c2fa1afcd70e70a6f49eefc93ecb"    
BOT_TOKEN = "8942265353:AAGIM-jipwy5QpQkruPMNEm3YDwmv0lZckI"    

# Tumhari permanent Render link
SERVER_URL = "https://petracts-stream.onrender.com" 

# Using in-memory session to avoid cloud storage locks
bot = TelegramClient(None, API_ID, API_HASH)
file_store = {}
routes = web.RouteTableDef()


# --- 1. CLEAN AUTO-PLAY CONTROLLER ---
@routes.get('/play/{file_id}')
async def player_handler(request):
    file_id = request.match_info['file_id']
    if file_id not in file_store:
        return web.Response(text="File Link Expired. Re-forward file to bot.", status=404)
        
    file_data = file_store[file_id]
    file_name = file_data["file_name"]
    stream_url = f"{SERVER_URL}/stream/{file_id}"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{file_name}</title>
        <style>
            body, html {{
                background-color: #000000; margin: 0; padding: 0;
                width: 100%; height: 100%; overflow: hidden;
                display: flex; justify-content: center; align-items: center;
            }}
            video {{
                width: 100%; height: 100%; outline: none;
                background: #000;
            }}
        </style>
    </head>
    <body>
        <video id="player" controls autoplay preload="metadata" crossorigin="anonymous" playsinline>
            <source src="{stream_url}" type="video/mp4">
        </video>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type='text/html')


# --- 2. HIGH-SPEED CLOUD CDN STREAMER ---
@routes.get('/stream/{file_id}')
async def stream_handler(request):
    file_id = request.match_info['file_id']
    if file_id not in file_store:
        return web.Response(text="Stream Not Found", status=404)

    file_data = file_store[file_id]
    media_obj = file_data["media"]
    file_size = file_data["file_size"]

    range_header = request.headers.get('Range', None)
    
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",
        "Access-Control-Allow-Origin": "*",
        "Connection": "keep-alive"
    }

    if not range_header:
        headers["Content-Length"] = str(file_size)
        return web.Response(status=200, headers=headers)

    match = re.search(r'bytes=(\d+)-(\d*)', range_header)
    if not match:
        return web.Response(status=400, text="Bad Range")

    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    chunk_size = (end - start) + 1

    headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    headers["Content-Length"] = str(chunk_size)

    response = web.StreamResponse(status=206, reason="Partial Content", headers=headers)
    await response.prepare(request)

    try:
        # Reduced chunk footprint to ensure free tier cloud RAM never chokes
        async for chunk in bot.iter_download(media_obj, offset=start, stride=256 * 1024):
            if not chunk or start > end:
                break
            if start + len(chunk) > end:
                chunk = chunk[:(end - start) + 1]
            await response.write(chunk)
            start += len(chunk)
    except Exception:
        pass

    return response


# --- 3. BOT MESSAGING RECEIVER ---
@bot.on(events.NewMessage(incoming=True))
async def handle_video(event):
    if event.message.video or event.message.document:
        msg = event.message
        
        file_id = f"{msg.chat_id}_{msg.id}"
        file_name = msg.file.name if (msg.file and msg.file.name) else "video.mp4"
        file_size = msg.file.size

        file_store[file_id] = {
            "media": msg.media,
            "file_name": file_name,
            "file_size": file_size
        }

        play_link = f"{SERVER_URL}/play/{file_id}"
        embed_code = f'<iframe src="{play_link}" width="100%" height="100%" frameborder="0" allowfullscreen></iframe>'

        reply_text = (
            f"🍿 Petracts Cloud Stream Core Online!\n\n"
            f"📂 File Name: {file_name}\n"
            f"🚀 Mode: High-Speed Direct Stream\n\n"
            f"🌐 Web Play Link:\n{play_link}\n\n"
            f"🛠️ Embed Code:\n{embed_code}"
        )
        await event.reply(reply_text)


# --- 4. ENGINE RUNNER ---
async def start_services():
    await bot.start(bot_token=BOT_TOKEN)
    
    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(start_services())