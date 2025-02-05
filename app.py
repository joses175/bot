import asyncio
import logging
import html
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import os

# ------------------------------
# Configurações
# ------------------------------
# Coloque seu token diretamente aqui (atenção: evite expor esse token em produção)
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------------------
# Funções Auxiliares
# ------------------------------
def safe_escape(text: str) -> str:
    """
    Escapa caracteres especiais de forma segura.
    """
    try:
        return html.escape(text).encode("utf-16", "surrogatepass").decode("utf-16") if text else ""
    except Exception as e:
        logger.error(f"Erro ao escapar texto: {e}")
        return "[Conteúdo não legível]"

async def notificar_erro(context: ContextTypes.DEFAULT_TYPE, error: Exception, user_id: int = None) -> None:
    """
    Notifica o administrador em caso de erro.
    """
    error_message = (
        f"❌ <b>Erro Detectado:</b>\n\n"
        f"<b>Detalhes:</b> {error}\n"
        f"<b>Usuário:</b> {user_id or 'Desconhecido'}"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=error_message, parse_mode="HTML")
    except Exception as e:
        logger.critical(f"Erro ao notificar o admin: {e}")

async def enviar_info_usuario(user_id: int, user_name: str, username: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Envia informações da nova interação para o administrador.
    """
    user_info = (
        f"👤 <b>Nova interação:</b>\n\n"
        f"🔹 <b>ID do Usuário:</b> <code>{user_id}</code>\n"
        f"🔹 <b>Nome:</b> {user_name}\n"
        f"🔹 <b>Username:</b> @{username if username != 'N/A' else 'N/A'}"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=user_info, parse_mode="HTML")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Captura e registra erros não tratados.
    """
    logger.error("Exceção não tratada:", exc_info=context.error)
    error_msg = "⚠️ Ocorreu um erro inesperado. Tente novamente mais tarde."
    if update and isinstance(update, Update):
        await update.effective_message.reply_text(error_msg)
    await notificar_erro(context, context.error)

# ------------------------------
# Handlers de Mensagens
# ------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Responde ao comando /start.
    """
    welcome_message = (
        "👋 <b>Olá, seja bem-vindo(a)!</b>\n\n"
        "❓ <b>Deseja enviar uma mensagem anônima?</b>\n\n"
        "🔒 <b>Sua identidade está completamente protegida!</b>\n"
        "📸 Envie fotos, vídeos ou GIFs\n"
        "⚠️ Botões e legendas serão removidos automaticamente"
    )
    await update.message.reply_text(welcome_message, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Responde ao comando /help com instruções de uso.
    """
    help_message = (
        "ℹ️ <b>Como usar o Bot Anônimo</b>\n\n"
        "1. Use o comando /start para iniciar.\n"
        "2. Envie uma mensagem de texto ou mídia (foto, vídeo, GIF).\n"
        "3. Sua mensagem será encaminhada ao administrador de forma anônima.\n"
        "4. Se enviar mídia, as legendas serão removidas e seu conteúdo será agrupado."
    )
    await update.message.reply_text(help_message, parse_mode="HTML")

async def receber_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Processa mensagens de texto, enviando uma cópia para o administrador e fazendo echo para o usuário.
    """
    try:
        user_id = update.message.chat_id
        user_name = update.message.from_user.first_name or "N/A"
        username = update.message.from_user.username or "N/A"
        mensagem = update.message.text

        mensagem_info = (
            f"📩 <b>Nova mensagem recebida:</b>\n\n"
            f"🔹 <b>ID do Usuário:</b> <code>{user_id}</code>\n"
            f"🔹 <b>Nome:</b> {user_name}\n"
            f"🔹 <b>Username:</b> @{username if username != 'N/A' else 'N/A'}\n\n"
            f"💬 <b>Mensagem:</b>\n{safe_escape(mensagem)}"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=mensagem_info, parse_mode="HTML")
        await update.message.reply_text(mensagem)
    except Exception as e:
        await notificar_erro(context, e, user_id=update.message.chat_id)

async def receber_midia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Processa mídias (foto, vídeo, GIF) e as agrupa para envio.
    """
    try:
        user_id = update.message.chat_id
        user_name = update.message.from_user.first_name or "N/A"
        username = update.message.from_user.username or "N/A"
        caption = safe_escape(update.message.caption or "")

        # Armazenamento do álbum do usuário
        user_albums = context.user_data.setdefault("albums", {})
        album = user_albums.setdefault(user_id, {
            "media": [],
            "original_captions": [],
            "timer": None,
            "user_info_sent": False
        })

        # Processar mídia conforme o tipo
        if update.message.photo:
            media = InputMediaPhoto(media=update.message.photo[-1].file_id)
            album["original_captions"].append(caption)
        elif update.message.video:
            media = InputMediaVideo(media=update.message.video.file_id)
            album["original_captions"].append(caption)
        elif update.message.animation:
            # Processa GIF separadamente (sem agrupar)
            await context.bot.send_animation(
                chat_id=ADMIN_ID,
                animation=update.message.animation.file_id,
                caption=caption
            )
            await context.bot.send_animation(
                chat_id=user_id,
                animation=update.message.animation.file_id,
                caption=None
            )
            return
        else:
            await update.message.reply_text("⚠️ Formato não suportado!")
            return

        album["media"].append(media)

        # Cancelar timer anterior, se existir, para evitar envios duplicados
        if album["timer"]:
            album["timer"].cancel()
        album["timer"] = asyncio.create_task(
            enviar_album(user_id, user_name, username, album, context)
        )
    except Exception as e:
        await notificar_erro(context, e, user_id=update.message.chat_id)

async def enviar_album(user_id: int, user_name: str, username: str, album: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Aguarda um breve intervalo e envia o álbum (agrupamento de mídias) para o administrador e para o usuário.
    """
    await asyncio.sleep(3)
    if album["media"]:
        try:
            admin_media = []
            user_media = []
            
            for i, media in enumerate(album["media"]):
                admin_caption = album["original_captions"][i] if i == 0 else None
                if isinstance(media, InputMediaPhoto):
                    admin_media.append(InputMediaPhoto(
                        media=media.media,
                        caption=admin_caption
                    ))
                    user_media.append(InputMediaPhoto(media=media.media))
                else:
                    admin_media.append(InputMediaVideo(
                        media=media.media,
                        caption=admin_caption
                    ))
                    user_media.append(InputMediaVideo(media=media.media))
                    
            # Enviar informações do usuário (apenas uma vez)
            if not album["user_info_sent"]:
                await enviar_info_usuario(user_id, user_name, username, context)
                album["user_info_sent"] = True

            # Envia os grupos de mídia em chunks (máximo 10 por envio)
            for chunk in [admin_media[i:i+10] for i in range(0, len(admin_media), 10)]:
                await context.bot.send_media_group(chat_id=ADMIN_ID, media=chunk)
            for chunk in [user_media[i:i+10] for i in range(0, len(user_media), 10)]:
                await context.bot.send_media_group(chat_id=user_id, media=chunk)

        except Exception as e:
            await notificar_erro(context, e, user_id=user_id)
        finally:
            album["media"].clear()
            album["original_captions"].clear()
            album["user_info_sent"] = False

# ------------------------------
# Função Principal
# ------------------------------
def main() -> None:
    """
    Configuração e inicialização do bot.
    """
    logger.info("🤖 Bot Anônimo Iniciado")
    app = Application.builder().token(BOT_TOKEN).build()

    # Registrando handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_texto))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.ANIMATION,
        receber_midia
    ))
    app.add_error_handler(error_handler)

    # Inicia o polling
    app.run_polling()

if __name__ == "__main__":
    main()
