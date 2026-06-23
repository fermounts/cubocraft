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


def extraer_texto_imagen(media_url: str, auth=None) -> str:
    try:
        import pytesseract
        from PIL import Image

        resp = requests.get(media_url, auth=auth, timeout=15)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        texto = pytesseract.image_to_string(img, lang="spa")
        logger.info("OCR extracted %d chars", len(texto))
        return texto.strip()
    except Exception as e:
        logger.error("OCR error: %s", e)
        return ""


def _parsear_monto_ocr(texto: str) -> float | None:
    """Extrae el primer monto monetario del texto OCR. Soporta formato ARG (punto=miles, coma=decimal)."""
    import re
    patron = r'\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)'
    for m in re.findall(patron, texto):
        try:
            valor = float(m.replace(".", "").replace(",", "."))
            if valor >= 100:  # ignorar números pequeños (fechas, códigos, etc.)
                return valor
        except ValueError:
            continue
    return None


def validar_comprobante_imagen(media_url: str) -> tuple[bool, str, float | None]:
    auth = None
    if config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN:
        auth = (config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)

    texto = extraer_texto_imagen(media_url, auth=auth)
    keywords = ["transferencia", "pago", "comprobante", "monto", "importe", "$", "mp", "mercadopago"]
    encontrados = [kw for kw in keywords if kw in texto.lower()]
    es_valido = len(encontrados) >= 2
    monto_ocr = _parsear_monto_ocr(texto)
    logger.info("Comprobante validation: valid=%s encontrados=%s monto_ocr=%s", es_valido, encontrados, monto_ocr)
    return es_valido, texto, monto_ocr
