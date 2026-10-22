
import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv
import psycopg
from telegram import Update
from telegram.ext import ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

BASE_DIR = Path(__file__).resolve().parent
HISTORY_FILE = BASE_DIR / "history.json"
APPROVED_FILE = BASE_DIR / "approved.json"
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.ext import MessageHandler, filters

load_dotenv(BASE_DIR / ".env")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY")


def init_db():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is missing in Vercel.")

    with psycopg.connect(DATABASE_URL, sslmode="require") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS job_history (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    transcript TEXT NOT NULL,
                    scripts JSONB NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS approved_scripts (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    script TEXT NOT NULL
                )
            """)


def save_history(transcript, scripts):
    try:
        init_db()
        from psycopg.types.json import Jsonb

        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO job_history (transcript, scripts)
                    VALUES (%s, %s)
                    """,
                    (transcript, Jsonb(scripts))
                )
        print("History saved to Neon database.")

    except Exception as e:
        print(f"Database history save error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Content Repurposing Bot! "
        "Send /help to see available commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show help\n"
        "/history - View previous jobs (coming soon)"
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        init_db()

        with psycopg.connect(DATABASE_URL, sslmode="require") as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT scripts
                    FROM job_history
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
                row = cur.fetchone()

        if not row:
            await update.message.reply_text(
                "No previous jobs have been saved yet."
            )
            return

        scripts = row[0]

        await update.message.reply_text("Latest transcript scripts:")

        for script in scripts:
            await update.message.reply_text(
                script,
                reply_markup=create_buttons()
            )

    except Exception as e:
        print(f"History database error: {e}")
        await update.message.reply_text(
            "History could not be retrieved. Please try again."
        )

async def approved_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        init_db()

        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT script
                    FROM approved_scripts
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
                rows = cur.fetchall()

        if not rows:
            await update.message.reply_text(
                "No approved scripts saved yet."
            )
            return

        await update.message.reply_text("Approved scripts:")

        for row in rows:
            await update.message.reply_text(row[0])

    except Exception as e:
        print(f"Approved scripts error: {e}")
        await update.message.reply_text(
            "Could not retrieve approved scripts."
        )



def create_buttons():
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data="approve"),
            InlineKeyboardButton("🔄 Regenerate", callback_data="regenerate"),
            InlineKeyboardButton("❌ Reject", callback_data="reject"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def handle_transcript(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    context.user_data["last_transcript"] = text

    if len(text) < 100:
        await update.message.reply_text(
            "Please send a longer transcript (at least 100 characters)."
        )
        return

    await update.message.reply_text("Generating 5 scripts...")
    scripts = create_scripts(text)
    save_history(text, scripts)

    for script in scripts:
        await update.message.reply_text(
            script,
            reply_markup=create_buttons()
        )

    
        await update.message.reply_text("Generating static post ideas...")
        post_ideas = create_post_ideas(transcript)
        await update.message.reply_text(
            "📝 STATIC POST IDEAS\n\n" + post_ideas
        )

        try:
            await update.message.reply_text("🎨 Generating AI poster...")
            poster_path = generate_poster_image(
                "Key takeaway from the transcript"
            )

            with open(poster_path, "rb") as poster:
                await update.message.reply_photo(
                    photo=poster,
                    caption="AI-generated poster"
                )
        except Exception as e:
            print(f"Poster error: {type(e).__name__}: {e}")
            await update.message.reply_text(
                "Poster could not be generated."
            )

    except Exception as e:
        await update.message.reply_text(f"Poster error: {type(e).__name__}: {e}")
        await update.message.reply_text("Poster could not be generated.")







async def handle_transcript_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    filename = document.file_name or ""

    if not filename.lower().endswith((".txt", ".srt", ".vtt")):
        await update.message.reply_text(
            "Please upload a .txt, .srt, or .vtt transcript file."
        )
        return

    try:
        telegram_file = await context.bot.get_file(document.file_id)
        file_bytes = await telegram_file.download_as_bytearray()
        transcript = bytes(file_bytes).decode("utf-8-sig", errors="replace").strip()

        if len(transcript) < 100:
            await update.message.reply_text(
                "The transcript is too short."
            )
            return

        context.user_data["last_transcript"] = transcript
        await update.message.reply_text("Generating 5 scripts...")

        scripts = create_scripts(transcript)
        save_history(transcript, scripts)

        for script in scripts:
            await update.message.reply_text(
                script,
                reply_markup=create_buttons()
            )

        await update.message.reply_text("Generating static post ideas...")
        post_ideas = create_post_ideas(transcript)
        await update.message.reply_text(
            "📝 STATIC POST IDEAS\n\n" + post_ideas
        )

    except Exception as e:
        print(f"File processing error: {e}")
        await update.message.reply_text(
            "Could not process this file. Please try again."
        )




def create_post_ideas(transcript):
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "AI setup error: GROQ_API_KEY is missing."

    client = Groq(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Create exactly 5 static social media post ideas "
                        "using only the supplied transcript. Do not invent "
                        "facts. For each idea include HEADLINE, SHORT TEXT, "
                        "and CAPTION. Include relevant HASHTAGS. "
                        "Separate ideas clearly. Return plain text."
                    )
                },
                {
                    "role": "user",
                    "content": transcript
                }
            ],
            temperature=0.5,
        )

        return response.choices[0].message.content or (
            "No post ideas were generated."
        )

    except Exception as e:
        print(f"Post ideas error: {e}")
        return "Could not generate post ideas. Please try again."
def generate_poster_image(headline):
    import os
    import io
    import textwrap
    import urllib.request
    import urllib.parse
    from PIL import Image, ImageDraw, ImageFont

    api_key = os.getenv("POLLINATIONS_API_KEY")
    if not api_key:
        raise ValueError("POLLINATIONS_API_KEY is missing.")

    prompt = (
        "Create a professional vertical social media poster background. "
        "Modern composition, attractive lighting, clean design, "
        "no words, no letters, no typography. Theme: " + headline
    )

    url = (
        "https://gen.pollinations.ai/image/"
        + urllib.parse.quote(prompt, safe="")
        + "?model=flux&width=1024&height=1024"
    )

    request = urllib.request.Request(
        url,
        headers={"Authorization": "Bearer " + api_key}
    )
    print("Poster API request started")
    print("Pollinations API key exists:", bool(api_key))
    with urllib.request.urlopen(request, timeout=180) as response:
        image_bytes = response.read()

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image)

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font = ImageFont.truetype(font_path, 52)
    except OSError:
        font = ImageFont.load_default()

    lines = textwrap.wrap(headline, width=22)
    y = image.height - 100 - len(lines) * 65

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=2)
        x = (image.width - (bbox[2] - bbox[0])) // 2

        draw.text(
            (x, y),
            line,
            font=font,
            fill="white",
            stroke_width=2,
            stroke_fill="black"
        )
        y += 65

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90)
    output.seek(0)
    return output

def create_scripts(transcript):
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY is missing from .env")
        return ["AI setup error. Check the terminal."]

    client = Groq(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {
                    "role": "system",
                    
"content": (
    "Create exactly 5 different short video scripts "
    "using only the transcript. Do not invent facts. "
    "Number them SCRIPT 1, SCRIPT 2, SCRIPT 3, "
    "SCRIPT 4, and SCRIPT 5. "
    "Each script must include HOOK, BODY, CTA, "
    "CAPTION, HASHTAGS, and SOURCE REFERENCE. "
    "For SOURCE REFERENCE, include an exact short phrase "
    "copied from the transcript that supports the script. "
    "If the transcript contains timestamps or line numbers, "
    "include the relevant ones exactly as provided. "
    "Never invent timestamps or line numbers. "
    "If unavailable, write Timestamp/line unavailable. "
    "Keep each script suitable for a 30-60 second video. "
    "Separate each script with a blank line. "
    "Return plain text, not JSON."
)

                    
                },
                {
                    "role": "user",
                    "content": transcript
                }
            ],
            temperature=0.8,
        )

        result = response.choices[0].message.content or ""
        print("AI CONTENT:", repr(result))

        import re

        markers = list(re.finditer(
            r"(?im)^\s*\**\s*SCRIPT\s*[1-5]\s*\**\s*:?\s*$",
            result
        ))

        scripts = []
        for i, marker in enumerate(markers):
            start = marker.end()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(result)
            script = result[start:end].strip()
            if script:
                scripts.append(script)

        scripts = scripts[:5]

        if len(scripts) != 5:
            raise ValueError(
                f"Expected 5 scripts, but received {len(scripts)}."
            )

        return [
            f"Script {i + 1}\n\n{script}"
            for i, script in enumerate(scripts)
        ]

    except Exception as e:
        print(f"Groq AI error: {e}")
        return ["AI could not generate scripts. Check the terminal."]






async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "approve":
        script = query.message.text or ""

        try:
            init_db()

            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO approved_scripts (script) VALUES (%s)",
                        (script,)
                    )

            await query.message.reply_text(
                "✅ Script approved and saved permanently!"
            )

        except Exception as e:
            print(f"Approval save error: {e}")
            await query.message.reply_text(
                "Could not save approval. Please try again."
            )

    elif query.data == "regenerate":
        try:
            init_db()

            with psycopg.connect(DATABASE_URL, sslmode="require") as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT transcript
                        FROM job_history
                        ORDER BY created_at DESC
                        LIMIT 1
                    """)
                    row = cur.fetchone()

            if not row:
                await query.message.reply_text(
                    "No previous transcript found. Please send it again."
                )
                return

            transcript = row[0]

        except Exception as e:
            print(f"Transcript retrieval error: {e}")
            await query.message.reply_text(
                "Could not retrieve the previous transcript."
            )
            return

        scripts = create_scripts(transcript)

        import random
        script = random.choice(scripts)

        await query.message.reply_text(
            script,
            reply_markup=create_buttons()
        )

    elif query.data == "reject":
        await query.message.reply_text("❌ Script rejected.")

def main():
    if not TOKEN:
        raise ValueError("Bot token is missing from .env")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("history", history_command)) 
    app.add_handler(CommandHandler("approved", approved_command))  
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_transcript_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transcript))

    app.run_polling()


if __name__ == "__main__":
    main()
