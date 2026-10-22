
import os
import sys
import json
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from telegram import Update
from main import (
    start,
    help_command,
    history_command,
    approved_command,
    handle_transcript,
    handle_transcript_file,
    button_handler,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


ALLOWED_USER_IDS = {5087094983}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/api/webhook":
            self.send_error(404)
            return

        if not TOKEN:
            self.send_error(500, "Bot token not configured")
            return

        import asyncio

        async def process():
            app = (
                Application.builder()
                .token(TOKEN)
                .build()
            )

            app.add_handler(CommandHandler("start", start))
            app.add_handler(CommandHandler("help", help_command))
            app.add_handler(CommandHandler("history", history_command))
            app.add_handler(CommandHandler("approved", approved_command))
            app.add_handler(CallbackQueryHandler(button_handler))
            app.add_handler(
                MessageHandler(
                    filters.Document.ALL,
                    handle_transcript_file,
                )
            )
            app.add_handler(
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_transcript,
                )
            )

            await app.initialize()
            try:
                data = json.loads(body)
                update = Update.de_json(data, app.bot)


                if update.effective_user and update.effective_user.id not in ALLOWED_USER_IDS:
                    return

                await app.process_update(update)
            finally:
                await app.shutdown()

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            asyncio.run(process())

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception:
            self.send_error(500, "Webhook processing failed")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot endpoint is running")
