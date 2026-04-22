import logging
import os

from flask import Flask, jsonify, request, send_from_directory

import bot_handler
import whatsapp_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


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
    port = int(os.getenv("PORT", 5000))
    logger.info("Starting CUBOCRAFT on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
