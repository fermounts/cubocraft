import io
import logging

import requests
from twilio.rest import Client

import config

logger = logging.getLogger(__name__)

_twilio: Client | None = None


def _get_twilio() -> Client:
    global _twilio
    if _twilio is None:
        _twilio = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _twilio


def enviar(phone: str, mensaje: str, provider: str = "twilio") -> None:
    if provider == "evolution":
        _enviar_evolution(phone, mensaje)
    else:
        _enviar_twilio(phone, mensaje)


def _enviar_twilio(phone: str, mensaje: str) -> None:
    if not config.TWILIO_ACCOUNT_SID or not config.TWILIO_AUTH_TOKEN:
        logger.error("TWILIO_ACCOUNT_SID o TWILIO_AUTH_TOKEN no configurados — mensaje no enviado a %s", phone)
        return
    if not config.TWILIO_PHONE_NUMBER:
        logger.error("TWILIO_PHONE_NUMBER no configurado — mensaje no enviado a %s", phone)
        return
    try:
        to = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
        frm = config.TWILIO_PHONE_NUMBER
        if not frm.startswith("whatsapp:"):
            frm = f"whatsapp:{frm}"
        msg = _get_twilio().messages.create(body=mensaje, from_=frm, to=to)
        logger.info("Twilio message sent: %s → %s", msg.sid, phone)
    except Exception as e:
        logger.error("Error sending Twilio message to %s: %s", phone, e)


def _enviar_evolution(phone: str, mensaje: str) -> None:
    # Implement Evolution API REST call here when endpoint is available
    logger.info("[Evolution stub] to=%s: %r", phone, mensaje)


def notificar_supervisora(mensaje: str) -> None:
    phone = config.SUPERVISORA_PHONE
    if phone:
        enviar(phone, mensaje)
        logger.info("Supervisor notified")
    else:
        logger.warning("SUPERVISORA_PHONE not configured — notification skipped")


def _analizar_comprobante_gemini(media_url: str, auth=None) -> tuple[str, float | None]:
    """Descarga la imagen y usa Gemini Vision para extraer texto y monto del comprobante."""
    import re
    import base64
    import google.generativeai as genai

    try:
        resp = requests.get(media_url, auth=auth, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        b64 = base64.b64encode(resp.content).decode()

        genai.configure(api_key=config.GEMINI_API_KEY)
        modelo = genai.GenerativeModel("gemini-2.5-flash")
        resultado = modelo.generate_content([
            {
                "inline_data": {"mime_type": content_type, "data": b64}
            },
            (
                "Analizá esta imagen de comprobante de pago argentino. "
                "Respondé SOLO con JSON con exactamente estas dos claves: "
                '{"texto": "<todo el texto visible en la imagen>", "monto": <número o null>}. '
                "En 'monto' poné el monto total transferido como número sin símbolos (ej: 6000.0). "
                "Si no podés determinarlo con certeza, poné null."
            ),
        ])
        raw = resultado.text.strip().strip("```json").strip("```").strip()
        data = __import__("json").loads(raw)
        texto = data.get("texto", "")
        monto = float(data["monto"]) if data.get("monto") is not None else None
        logger.info("Gemini Vision: monto_ocr=%s texto_len=%d", monto, len(texto))
        return texto, monto

    except Exception as e:
        logger.error("Gemini Vision OCR error: %s", e)
        return "", None


def validar_comprobante_imagen(media_url: str) -> tuple[bool, str, float | None]:
    auth = None
    if config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN:
        auth = (config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)

    texto, monto_ocr = _analizar_comprobante_gemini(media_url, auth=auth)
    keywords = ["transferencia", "pago", "comprobante", "monto", "importe", "$", "mp", "mercadopago"]
    encontrados = [kw for kw in keywords if kw in texto.lower()]
    es_valido = len(encontrados) >= 2
    logger.info("Comprobante validation: valid=%s encontrados=%s monto_ocr=%s", es_valido, encontrados, monto_ocr)
    return es_valido, texto, monto_ocr
