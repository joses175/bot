from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.helpers import escape_markdown
import sqlite3

# Configuração inicial do banco de dados
conn = sqlite3.connect('bot_data.db', check_same_thread=False)
cursor = conn.cursor()

# Criar tabela caso não exista
cursor.execute('''
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    media_type TEXT,
    media_file_id TEXT,
    status TEXT DEFAULT 'pending',
    rejection_reason TEXT
)
''')
conn.commit()

# IDs fixos
ADMIN_ID = 6460184219
GROUP_ID = -1002424564273
BOT_USERNAME = "Anonimas175_bot"  # Substituir pelo username do seu bot (sem @)

# Função para dar boas-vindas
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 *Bem-vindo!*\n\n"
        "📋 *Como funciona:*\n"
        "1️⃣ Envie uma única mídia (foto ou vídeo) por vez.\n"
        "2️⃣ A mídia será analisada por um administrador.\n"
        "3️⃣ Após aprovação, será enviada ao grupo.\n\n"
        "🔒 *Todos os envios são 100% anônimos!* Ninguém saberá quem enviou a mídia.\n\n"
    )
    escaped_message = escape_markdown(welcome_message, version=2)
    await update.message.reply_text(escaped_message, parse_mode="MarkdownV2")

# Receber mídias enviadas pelo usuário
async def receber_midia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    username = update.message.from_user.username or "Usuário sem username"
    first_name = update.message.from_user.first_name or "Usuário sem nome"

    # Verificar se é foto ou vídeo
    if update.message.photo:
        media_type = "photo"
        media_file_id = update.message.photo[-1].file_id
    elif update.message.video:
        media_type = "video"
        media_file_id = update.message.video.file_id
    else:
        await update.message.reply_text("Por favor, envie uma foto ou vídeo válido.")
        return

    # Salvar a mídia no banco de dados
    cursor.execute(
        "INSERT INTO media (user_id, username, media_type, media_file_id) VALUES (?, ?, ?, ?)",
        (user_id, username, media_type, media_file_id),
    )
    conn.commit()
    media_id = cursor.lastrowid

    # Enviar informações ao administrador, incluindo o nome de usuário e o primeiro nome
    await context.bot.send_message(
        ADMIN_ID,
        text=(f"📩 *Nova mídia recebida para análise (envio anônimo):*\n\n"
              f"🔑 *UserID:* `{user_id}`\n"
              f"👤 *Username:* @{username}\n"
              f"📝 *Nome:* {first_name}\n"
              f"🆔 *Mídia ID:* `{media_id}`\n"
              "⚠️ *Envio anônimo: Ninguém saberá quem enviou.*"),
        parse_mode="Markdown",
    )

    # Criar botões de aprovação/reprovação
    buttons = [
        [
            InlineKeyboardButton("✅ Aprovar", callback_data=f"aprovar_{media_id}"),
            InlineKeyboardButton("❌ Reprovar", callback_data=f"reprovar_{media_id}")
        ]
    ]

    # Enviar a mídia para o administrador
    if media_type == "photo":
        await context.bot.send_photo(
            ADMIN_ID,
            media_file_id,
            caption=f"📷 *Foto enviada para análise*\n\n🆔 *Mídia ID:* `{media_id}`\n⚠️ *Envio Anônimo*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif media_type == "video":
        await context.bot.send_video(
            ADMIN_ID,
            media_file_id,
            caption=f"🎥 *Vídeo enviado para análise*\n\n🆔 *Mídia ID:* `{media_id}`\n⚠️ *Envio Anônimo*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    # Informar ao usuário que a mídia foi enviada
    await update.message.reply_text("Sua mídia foi enviada para análise. O envio é anônimo e ninguém saberá quem a enviou.")

# Callback para aprovar ou reprovar mídias
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data.startswith("aprovar_"):
        media_id = int(data.split("_")[1])
        cursor.execute("SELECT user_id, media_file_id, media_type FROM media WHERE id = ?", (media_id,))
        media = cursor.fetchone()

        if media:
            user_id, media_file_id, media_type = media

            # Enviar a mídia para o grupo
            if media_type == "photo":
                await context.bot.send_photo(GROUP_ID, media_file_id, caption=f"📷 #envioanônimo \n @{BOT_USERNAME}")
            elif media_type == "video":
                await context.bot.send_video(GROUP_ID, media_file_id, caption=f"🎥 #envioanônimo \n @{BOT_USERNAME}")

            # Atualizar status no banco de dados
            cursor.execute("UPDATE media SET status = 'approved' WHERE id = ?", (media_id,))
            conn.commit()

            # Informar ao administrador
            await query.message.reply_text("✅ Aprovado: A mídia foi enviada ao grupo.")

            # Notificar o usuário
            await context.bot.send_message(
                user_id,
                "✅ Sua mídia foi aprovada e enviada ao grupo. O envio foi anônimo e ninguém saberá quem a enviou."
            )

    elif data.startswith("reprovar_"):
        media_id = int(data.split("_")[1])

        # Salvar no contexto para aguardar o motivo
        context.user_data["awaiting_reason"] = media_id

        # Solicitar o motivo da reprovação
        await query.message.reply_text("❌ Por favor, envie o motivo da reprovação como uma mensagem de texto.")

# Receber o motivo da reprovação
async def receber_motivo_reprovacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    media_id = context.user_data.get("awaiting_reason")

    if media_id:
        motivo = update.message.text
        cursor.execute("SELECT user_id FROM media WHERE id = ?", (media_id,))
        media = cursor.fetchone()

        if media:
            user_id = media[0]

            # Atualizar o banco de dados com o motivo
            cursor.execute("UPDATE media SET status = 'rejected', rejection_reason = ? WHERE id = ?", (motivo, media_id))
            conn.commit()

            # Informar o administrador
            await update.message.reply_text("❌ Rejeição registrada e enviada ao usuário.")

            # Notificar o usuário
            await context.bot.send_message(
                user_id,
                f"❌ Sua mídia foi reprovada.\n\n📋 *Motivo:* {motivo}\n\n⚠️ *Envio Anônimo: Ninguém sabe quem enviou.*",
                parse_mode="Markdown",
            )

            # Limpar o contexto
            del context.user_data["awaiting_reason"]
        else:
            await update.message.reply_text("⚠️ Mídia não encontrada para registrar o motivo.")
    else:
        await update.message.reply_text("⚠️ Não há nenhuma reprovação pendente.")

# Configuração principal
def main():
    print("Inicializando o bot...")
    application = Application.builder().token("7702255202:AAHcxWp63HOFJgJpkYEtiGxHmFvx08nBpmY").build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, receber_midia))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_motivo_reprovacao))
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    # Iniciar bot
    application.run_polling()

if __name__ == "__main__":
    main()
