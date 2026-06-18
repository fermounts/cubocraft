import functools
import logging
import os
import re

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, jsonify, request, send_from_directory, send_file, session
import pathlib
import pytz

import bot_handler
import config
import sheets_client
import whatsapp_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

_STATIC_DIR = pathlib.Path(__file__).parent / "static"
_BASE_DIR    = pathlib.Path(__file__).parent

app = Flask(__name__, static_folder=str(_STATIC_DIR), static_url_path="/static")
app.secret_key = config.SECRET_KEY


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


@app.after_request
def add_cache_headers(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


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
    logger.info("━━━ WEBHOOK IN ━━━ content-type=%r", content_type)

    # ── Extraer datos del request ────────────────────────────────────────────
    try:
        if "application/json" in content_type:
            data = request.get_json(force=True, silent=True) or {}
            logger.info("Evolution payload keys: %s", list(data.keys()))
            phone, text, media_url = _extract_evolution(data)
            provider = "evolution"
        else:
            form = dict(request.form)
            logger.info("Twilio form keys: %s", list(form.keys()))
            logger.info("Twilio From=%r Body=%r NumMedia=%r",
                        form.get("From"), form.get("Body"), form.get("NumMedia"))
            phone, text, media_url = _extract_twilio(request)
            provider = "twilio"
    except Exception:
        logger.exception("ERROR extrayendo datos del request")
        return jsonify({"status": "parse_error"}), 200

    if not phone:
        logger.warning("Phone vacío — request ignorado. Form: %s", dict(request.form))
        return jsonify({"status": "ignored"}), 200

    logger.info("phone=%r provider=%r text=%r media=%s", phone, provider, text, bool(media_url))

    # ── Procesar con el bot ──────────────────────────────────────────────────
    try:
        respuesta = bot_handler.procesar(phone, text, media_url=media_url)
        logger.info("bot respuesta len=%d: %r", len(respuesta or ""), (respuesta or "")[:80])
    except Exception:
        logger.exception("ERROR no manejado en bot_handler.procesar() phone=%r text=%r", phone, text)
        return jsonify({"status": "bot_error"}), 200

    # ── Enviar respuesta ─────────────────────────────────────────────────────
    if respuesta:
        try:
            whatsapp_client.enviar(phone, respuesta, provider=provider)
        except Exception:
            logger.exception("ERROR enviando respuesta a phone=%r", phone)
    else:
        logger.warning("Bot devolvió respuesta vacía para phone=%r text=%r", phone, text)

    return jsonify({"status": "ok"}), 200


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "app": "CUBOCRAFT"}), 200


@app.route("/debug-config")
def debug_config():
    """Muestra qué variables de entorno están seteadas (sin exponer valores)."""
    import config as cfg
    vars_status = {
        "TWILIO_ACCOUNT_SID":  bool(cfg.TWILIO_ACCOUNT_SID),
        "TWILIO_AUTH_TOKEN":   bool(cfg.TWILIO_AUTH_TOKEN),
        "TWILIO_PHONE_NUMBER": bool(cfg.TWILIO_PHONE_NUMBER),
        "TWILIO_PHONE_NUMBER_value": (cfg.TWILIO_PHONE_NUMBER or "")[:6] + "..." if cfg.TWILIO_PHONE_NUMBER else "(vacío)",
        "GOOGLE_SHEET_ID":     bool(cfg.GOOGLE_SHEET_ID),
        "GOOGLE_CREDS_JSON":   bool(cfg.GOOGLE_CREDS_JSON),
        "GEMINI_API_KEY":      bool(cfg.GEMINI_API_KEY),
        "SUPERVISORA_PHONE":   bool(cfg.SUPERVISORA_PHONE),
        "SUPERVISORA_PHONE_value": cfg.SUPERVISORA_PHONE or "(vacío)",
    }
    return jsonify(vars_status), 200


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# ── Dashboard ─────────────────────────────────────────────────────────────────

def _login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "vid" not in session:
            return jsonify({"error": "no_auth"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/dashboard")
def dashboard():
    return send_file(str(_BASE_DIR / "dashboard.html"))


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    phone = str(data.get("phone", "")).strip()
    pin   = str(data.get("pin", "")).strip()
    if not phone or not pin:
        return jsonify({"error": "Teléfono y PIN requeridos"}), 400
    vendedor = sheets_client.validar_login(phone, pin)
    if not vendedor:
        return jsonify({"error": "Teléfono o PIN incorrecto"}), 401
    sup_phone = re.sub(r"[^\d]", "", config.SUPERVISORA_PHONE or "")
    v_phone   = re.sub(r"[^\d]", "", str(vendedor.get("Teléfono", "")))
    role = "supervisor" if (sup_phone and v_phone == sup_phone) else "vendedor"
    session["vid"]    = str(vendedor["ID"])
    session["nombre"] = str(vendedor["Nombre"])
    session["role"]   = role
    return jsonify({"ok": True, "nombre": vendedor["Nombre"], "role": role})


@app.route("/api/dashboard-data")
@_login_required
def api_dashboard_data():
    vid  = session["vid"]
    role = session["role"]
    if role == "supervisor":
        data = sheets_client.get_dashboard_supervisor()
    else:
        data = sheets_client.get_dashboard_vendedor(vid)
    return jsonify({"role": role, "nombre": session["nombre"], **data})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info("Starting CUBOCRAFT on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
