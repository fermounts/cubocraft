import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, jsonify, request, send_from_directory
import pytz

import bot_handler
import sheets_client
import whatsapp_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# ── Resumen diario al supervisor ──────────────────────────────────────────────

def _enviar_resumen_diario() -> None:
    try:
        pendientes = sheets_client.get_pendientes_del_dia()
        total = len(pendientes)
        sin_validar = sum(1 for p in pendientes if str(p.get("ESTADO", "")).lower() == "pendiente")
        mensaje = (
            f"CUBOCRAFT — Resumen del dia\n"
            f"Consultas tecnicas nuevas: {total}\n"
            f"Pendientes de validar: {sin_validar}\n"
            f"Revisa y valida en Google Sheets → PENDIENTES_VALIDACION"
        )
        whatsapp_client.notificar_supervisora(mensaje)
        logger.info("Resumen diario enviado: total=%d sin_validar=%d", total, sin_validar)
    except Exception as e:
        logger.error("Error enviando resumen diario: %s", e)


def _procesar_pendientes_job() -> None:
    try:
        n = sheets_client.procesar_pendientes_aprobados()
        if n:
            logger.info("Scheduler: %d pendiente(s) movido(s) a BASE_CONOCIMIENTO", n)
        else:
            logger.debug("Scheduler: sin pendientes aprobados para procesar")
    except Exception:
        logger.exception("Scheduler: error en procesar_pendientes_job")


_tz_arg = pytz.timezone("America/Argentina/Buenos_Aires")
_scheduler = BackgroundScheduler(timezone=_tz_arg)
_scheduler.add_job(
    _enviar_resumen_diario,
    CronTrigger(hour=20, minute=0, timezone=_tz_arg),
    id="resumen_diario",
    replace_existing=True,
)
_scheduler.add_job(
    _procesar_pendientes_job,
    "interval",
    hours=1,
    id="procesar_pendientes",
    replace_existing=True,
)
_scheduler.start()
logger.info("Scheduler iniciado — resumen 20:00 ARG | procesar_pendientes cada 1h")


def _extract_twilio(req):
    phone = req.form.get("From", "").replace("whatsapp:", "")
    text = req.form.get("Body", "").strip()
    media_url = req.form.get("MediaUrl0")
    return phone, text, media_url


def _extract_evolution(data: dict):
    try:
        msg_data = data.get("data", {})
        remote_jid = msg_data.get("key", {}).get("remoteJid", "")
        phone = remote_jid.replace("@s.whatsapp.net", "").replace("@g.us", "")
        msg = msg_data.get("message", {})
        text = (
            msg.get("conversation")
            or msg.get("extendedTextMessage", {}).get("text")
            or ""
        ).strip()
        media_url = msg.get("imageMessage", {}).get("url")
        return phone, text, media_url
    except Exception as e:
        logger.error("Error parsing Evolution payload: %s", e)
        return None, None, None


@app.route("/webhook", methods=["POST"])
def webhook():
    content_type = request.content_type or ""
    logger.info("Webhook received | content-type: %s", content_type)

    if "application/json" in content_type:
        data = request.get_json(force=True, silent=True) or {}
        logger.info("Evolution payload keys: %s", list(data.keys()))
        phone, text, media_url = _extract_evolution(data)
        provider = "evolution"
    else:
        logger.info("Twilio form data: %s", dict(request.form))
        phone, text, media_url = _extract_twilio(request)
        provider = "twilio"

    if not phone:
        logger.warning("Could not extract phone from request")
        return jsonify({"status": "ignored"}), 200

    logger.info("Message from %s [%s]: %r | media=%s", phone, provider, text, bool(media_url))

    respuesta = bot_handler.procesar(phone, text, media_url=media_url)
    if respuesta:
        whatsapp_client.enviar(phone, respuesta, provider=provider)

    return jsonify({"status": "ok"}), 200


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "app": "CUBOCRAFT"}), 200


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info("Starting CUBOCRAFT on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
