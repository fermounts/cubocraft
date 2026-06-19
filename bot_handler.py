import logging
import os
from datetime import datetime

import google.generativeai as genai

import config
import session_store
import sheets_client
import whatsapp_client

logger = logging.getLogger(__name__)

# ── Estados ───────────────────────────────────────────────────────────────────
ELEGIR_EMPRESA = "ELEGIR_EMPRESA"
MENU = "MENU"
PEDIDO_CATEGORIA = "PEDIDO_CATEGORIA"
PEDIDO_PRODUCTOS = "PEDIDO_PRODUCTOS"
PEDIDO_CANTIDAD = "PEDIDO_CANTIDAD"
PEDIDO_CONFIRMAR = "PEDIDO_CONFIRMAR"
PAGO_MONTO = "PAGO_MONTO"
PAGO_METODO = "PAGO_METODO"
PAGO_COMPROBANTE = "PAGO_COMPROBANTE"
PAGO_CONFIRMAR = "PAGO_CONFIRMAR"
BAJA_CONFIRMAR = "BAJA_CONFIRMAR"
CONSULTA_IA = "CONSULTA_IA"
POST_ACCION = "POST_ACCION"
SUPER_CANDIDATAS = "SUPER_CANDIDATAS"
CANCELAR_PEDIDO = "CANCELAR_PEDIDO"
CANCELAR_PEDIDO_CONFIRM = "CANCELAR_PEDIDO_CONFIRM"
ANULAR_PAGO = "ANULAR_PAGO"
ANULAR_PAGO_CONFIRM = "ANULAR_PAGO_CONFIRM"
SUPER_MENU = "SUPER_MENU"
SUPER_CONFIRMAR_PAGO = "SUPER_CONFIRMAR_PAGO"
SUPER_CONFIRMAR_PAGO_CONFIRM = "SUPER_CONFIRMAR_PAGO_CONFIRM"

# ── Categorías de producto por empresa ────────────────────────────────────────
# (clave en Apertura, nombre de display)
_CATEGORIAS: dict[str, list[tuple[str, str]]] = {
    "CUBO": [
        ("Cabeza",       "🪖 Cabeza — Cascos"),
        ("Calzado",      "👢 Calzado"),
        ("Visual",       "🥽 Visual"),
        ("Auditiva",     "🎧 Auditiva"),
        ("Manos",        "🧤 Manos y guantes"),
        ("Altura",       "🪢 Altura y arneses"),
        ("Respiratoria", "😷 Respiratoria"),
        ("Cuerpo",       "🦺 Cuerpo"),
    ],
    "CRAFT": [
        ("Mamposteria",        "🧱 Mampostería y estructuras"),
        ("Construccion_seco",  "🏗️ Construcción en seco"),
        ("Impermeabilizacion", "💧 Impermeabilización"),
        ("Terminaciones",      "🎨 Terminaciones"),
        ("Aislacion",          "🌡️ Aislación"),
        ("Reparaciones",       "🔧 Reparaciones"),
    ],
}

# ── Menú unificado ────────────────────────────────────────────────────────────
_MENU_MAP: dict[str, str] = {
    "1": "catalogo",
    "2": "pago",
    "3": "saldo",
    "4": "mis_pedidos",
    "5": "ranking",
    "6": "ia",
    "7": "supervisor",
    "8": "baja",
}

_COMANDOS_CONTROL = {"si", "sí", "no", "listo", "fin"}

_gemini_configured = False


def _configure_gemini() -> None:
    global _gemini_configured
    if not _gemini_configured:
        api_key = config.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
        prefix = (api_key[:4] + "...") if api_key else "(vacía)"
        logger.info("GEMINI_API_KEY prefix=%s len=%d", prefix, len(api_key))
        if not api_key:
            logger.error("GEMINI_API_KEY no está configurada — verificá la variable en Render")
            raise RuntimeError("GEMINI_API_KEY no configurada")
        genai.configure(api_key=api_key)
        _gemini_configured = True


def generar_mensaje_coaching(
    nombre: str,
    total_semana: float,
    aperturas_vendedor: list[str],
    aperturas_lider: list[str],
) -> str:
    """Mensaje de coaching con Gemini para el último puesto del ranking semanal."""
    cats_lider   = ", ".join(aperturas_lider)   if aperturas_lider   else "diversas categorías"
    cats_propias = ", ".join(aperturas_vendedor) if aperturas_vendedor else "sus categorías habituales"
    prompt = (
        f"Sos coach de ventas de CUBOCRAFT, empresa de EPP y materiales de construcción en Argentina.\n"
        f"Un vendedor llamado {nombre} cerró la semana con ${total_semana:,.2f} en ventas, "
        f"trabajando principalmente: {cats_propias}.\n"
        f"Las categorías más vendidas por el equipo esta semana fueron: {cats_lider}.\n\n"
        f"Escribí un mensaje de WhatsApp para {nombre} que:\n"
        f"- Reconozca su esfuerzo de la semana\n"
        f"- Sugiera explorar las categorías {cats_lider} sin aclarar que las lidera otro vendedor\n"
        f"- Tono de coach positivo, NO de regaño\n"
        f"- 3 párrafos máximo, lenguaje argentino natural\n"
        f"- Incluí algún emoji adecuado\n"
        f"- No menciones a ningún otro vendedor ni comparaciones\n"
        f"Solo devolvé el mensaje, sin explicaciones previas."
    )
    try:
        _configure_gemini()
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction="Sos coach de ventas en Argentina. Respondés solo con el mensaje solicitado.",
        )
        resp = model.generate_content(
            prompt,
            # gemini-2.5-flash usa tokens de thinking antes de responder;
            # max_output_tokens bajo los agota antes de producir texto real.
            generation_config=genai.GenerationConfig(max_output_tokens=8192),
        )
        # Concatenar todas las partes para no perder texto por streaming parcial
        text = "".join(p.text for p in resp.candidates[0].content.parts if hasattr(p, "text"))
        return text.strip() if text.strip() else resp.text.strip()
    except Exception as e:
        logger.error("generar_mensaje_coaching error: %s", e)
        return (
            f"💪 *¡Seguí adelante, {nombre}!*\n\n"
            f"Esta semana lograste ${total_semana:,.2f} en ventas — ¡cada pedido cuenta!\n\n"
            f"La próxima semana es una nueva oportunidad para explorar nuevas categorías y crecer. "
            f"El equipo confía en vos.\n\n— El equipo CUBOCRAFT"
        )


# ── Renders reutilizables ─────────────────────────────────────────────────────

def _selector_empresa(nombre: str) -> str:
    return (
        f"Hola {nombre}! 👋 ¿Con qué empresa querés operar?\n\n"
        "1️⃣ CUBO — Seguridad e Higiene 👷\n"
        "2️⃣ CRAFT — Métodos Constructivos 🏗️"
    )


def _menu_texto(empresa: str, es_supervisor: bool) -> str:
    header = "👷 *CUBO — Seguridad e Higiene*" if empresa == "CUBO" else "🏗️ *CRAFT — Métodos Constructivos*"
    base = (
        f"{header}\n\n"
        "1️⃣ Hacer un pedido\n"
        "2️⃣ Registrar un pago\n"
        "3️⃣ Ver mi saldo\n"
        "4️⃣ Mis pedidos\n"
        "5️⃣ Ranking del mes\n"
        "6️⃣ Consulta técnica IA 🤖\n"
        "7️⃣ Hablar con el supervisor\n"
        "8️⃣ Solicitar baja o pausa\n"
    )
    if es_supervisor:
        base += "9️⃣ Panel supervisor 🔒\n"
    return base


def _render_categorias(empresa: str, carrito: list) -> str:
    categorias = _CATEGORIAS.get(empresa, [])
    lines = []

    if carrito:
        lines.append("🛒 *Tu pedido:*")
        subtotal = 0.0
        for item in carrito:
            precio = float(item["producto"].get("Precio_Vendedor", 0))
            cantidad = item["cantidad"]
            desc_pct = item.get("descuento_pct", 0)
            total_item = round(precio * cantidad * (1 - desc_pct / 100), 0)
            subtotal += total_item
            lines.append(f"• {item['producto'].get('Nombre','?')} x{cantidad} = ${total_item:.0f}")
        lines.append(f"Subtotal: ${subtotal:.0f}\n")

    header = "👷 *CUBO — Elegí una categoría:*" if empresa == "CUBO" else "🏗️ *CRAFT — Elegí una categoría:*"
    lines.append(header)
    for i, (_, display) in enumerate(categorias, 1):
        lines.append(f"{i}. {display}")

    if carrito:
        lines.append("\nEscribí el número o *LISTO* para cerrar el pedido")
    else:
        lines.append("\nEscribí el número de categoría")
    lines.append("00 menú  |  000 cambiar empresa")
    return "\n".join(lines)


def _render_productos(clave: str, nombre_display: str, empresa: str) -> str:
    productos = sheets_client.get_productos_por_categoria(clave, empresa)
    if not productos:
        return (
            f"📦 *{nombre_display}*\n\n"
            "No hay productos disponibles en esta categoría aún.\n\n"
            "0 para volver a categorías"
        )
    lines = [f"📦 *{nombre_display}*\n"]
    for i, p in enumerate(productos, 1):
        lines.append(f"{i}. {p.get('Nombre','?')} — ${p.get('Precio_Vendedor','?')}")
    lines.append("\nEscribí el número o 0 para volver a categorías")
    return "\n".join(lines)


def _post_prompt() -> str:
    return "\n\n1️⃣ Volver al menú  |  2️⃣ Hasta pronto 👋"


def _es_pregunta_abierta(texto: str) -> bool:
    t = texto.strip().lower()
    if not t or t.isdigit():
        return False
    if t in _COMANDOS_CONTROL:
        return False
    if len(t) <= 6 and t.replace("-", "").replace("_", "").isalnum():
        return False
    return True


# ── Consulta IA (pipeline RAG con contexto completo) ──────────────────────────

def _detectar_fuente(respuesta: str) -> str:
    r = respuesta.lower()
    if "base cubocraft" in r:
        return "BASE_CONOCIMIENTO"
    if "conocimiento general" in r:
        return "IA_GENERAL"
    return "NORMATIVA"


def _ficha_a_contexto(r: dict) -> str:
    """Convierte un registro de BASE_CONOCIMIENTO a texto para el contexto de Gemini.

    Soporta dos estructuras coexistentes en la hoja:
    - Fichas técnicas (completar_sheet.py): nombre en CATEGORIA, apertura en PREGUNTA,
      DESCRIPCION en RESPUESTA_VALIDADA, MODO_USO en FUENTE_ORIGINAL.
    - Q&A validadas (pipeline PENDIENTES_VALIDACION): PREGUNTA real (>15 chars).
    """
    pregunta = str(r.get("PREGUNTA", "")).strip()
    respuesta = str(r.get("RESPUESTA_VALIDADA", "")).strip()

    if len(pregunta) > 15:
        # Registro Q&A del pipeline de validación
        cat = str(r.get("CATEGORIA", "")).strip()
        linea = f"P: {pregunta} | R: {respuesta}"
        return linea + (f" | Cat: {cat}" if cat else "")

    # Ficha técnica (mapeada a columnas Q&A por la estructura del Sheet)
    nombre = str(r.get("CATEGORIA", "")).strip()    # Nombre del producto
    tipo = pregunta                                   # Apertura / categoría
    descripcion = respuesta                           # DESCRIPCION
    modo_uso = str(r.get("FUENTE_ORIGINAL", "")).strip()

    partes = []
    if nombre:
        partes.append(f"Producto: {nombre}")
    if tipo:
        partes.append(f"Tipo: {tipo}")
    if descripcion:
        partes.append(f"Desc: {descripcion[:250]}")
    if modo_uso:
        partes.append(f"Uso: {modo_uso[:150]}")
    return " | ".join(partes)


def procesar_consulta_ia(texto_usuario: str, empresa: str) -> str:
    # Leer contexto RAG desde Sheets
    logger.info("RAG: leyendo BASE_CONOCIMIENTO...")
    try:
        base = sheets_client.get_base_conocimiento()
        logger.info("RAG: base_conocimiento=%d registros", len(base))
    except Exception:
        logger.exception("RAG: fallo al leer BASE_CONOCIMIENTO — se continúa sin base")
        base = []

    logger.info("RAG: leyendo CONOCIMIENTO_TECNICO...")
    try:
        normativas = sheets_client.get_conocimiento_tecnico()
        logger.info("RAG: normativas=%d registros", len(normativas))
    except Exception:
        logger.exception("RAG: fallo al leer CONOCIMIENTO_TECNICO — se continúa sin normativas")
        normativas = []

    ctx_base = "\n".join(
        line for r in base if (line := _ficha_a_contexto(r))
    ) or "Sin contenido técnico aún."

    ctx_norm = "\n".join(
        f"ID: {k.get('ID_Norma','')} | NORMA: {k.get('Nombre_Norma','')} | ALCANCE: {k.get('Alcance','')}"
        for k in normativas
    ) or "Sin normativas cargadas."

    linea = (
        "EPP (IRAM 3620 cascos, IRAM 3627 calzado, IRAM 3649 guantes, SRT 299/11)"
        if empresa == "CUBO"
        else "Métodos Constructivos (CIRSOC 201, IRAM 1597)"
    )
    system_text = (
        "Sos el Ingeniero Experto de CUBOCRAFT. "
        "Respondés en español, máximo 3 líneas cortas, sin markdown, sin asteriscos, sin negrita. Solo texto plano. "
        f"Línea de negocio activa: {linea}.\n\n"
        "Priorizá las RESPUESTAS VALIDADAS sobre tu conocimiento general. "
        "Si usás una respuesta validada indicá (fuente: base CUBOCRAFT). "
        "Si usás una normativa indicá la norma. "
        "Si respondés desde conocimiento general indicá (fuente: conocimiento general).\n\n"
        f"=== RESPUESTAS VALIDADAS CUBOCRAFT ===\n{ctx_base}\n\n"
        f"=== NORMATIVAS TÉCNICAS ===\n{ctx_norm}"
    )

    logger.info("RAG: iniciando consulta Gemini — empresa=%s pregunta=%r", empresa, texto_usuario[:80])
    try:
        _configure_gemini()
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_text,
        )
        resp = model.generate_content(
            texto_usuario,
            generation_config=genai.GenerationConfig(max_output_tokens=400),
        )
        respuesta = resp.text
        logger.info("RAG: Gemini respondió — len=%d", len(respuesta or ""))
    except RuntimeError as e:
        logger.exception("Gemini config error (API key o cliente): %s", e)
        return "Error de autenticación con IA. Contactá al administrador."
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in ("api key", "api_key", "authentication", "permission denied", "unauthenticated", "invalid")):
            logger.exception("Gemini auth error: %s", e)
            return "Error de autenticación con IA. Contactá al administrador."
        if any(k in msg for k in ("quota", "resource exhausted", "rate limit")):
            logger.exception("Gemini rate limit / quota: %s", e)
            return "Servicio de IA temporalmente no disponible. Intentá en unos minutos."
        logger.exception("Gemini error inesperado: %s", e)
        return "No pude procesar tu consulta. Intentá de nuevo."

    if not respuesta:
        logger.error("RAG: Gemini devolvió respuesta vacía o None — resp=%r", resp)
        return "No pude procesar tu consulta. Intentá de nuevo."

    fuente = _detectar_fuente(respuesta)
    logger.info("RAG: registrando pendiente fuente=%s", fuente)
    try:
        sheets_client.registrar_pendiente(texto_usuario, respuesta, fuente)
    except Exception:
        logger.exception("RAG: fallo al registrar pendiente — se devuelve respuesta igual")
    return respuesta


# ── Router principal ──────────────────────────────────────────────────────────

def procesar(phone: str, texto: str, media_url: str | None = None) -> str:
    logger.info("procesar() → phone=%r  texto=%r", phone, texto)
    texto = (texto or "").strip()
    t = texto.lower()

    # Ignorar silenciosamente mensajes de control del sandbox de Twilio
    if t.startswith("join ") or t == "join":
        logger.info("procesar() → mensaje de join sandbox ignorado para phone=%r", phone)
        return ""

    session = session_store.get(phone)
    estado = session.get("estado", MENU)
    logger.info("procesar() → estado=%r  empresa=%r", estado, session.get("empresa"))

    vendedor = session.get("vendedor") or sheets_client.get_vendedora_by_phone(phone)
    if not vendedor:
        logger.warning("procesar() → vendedor no encontrado para phone=%r", phone)
        return (
            "👋 Hola! Soy el asistente de *CUBOCRAFT*.\n"
            "No encontré tu cuenta registrada. "
            "Contactá a tu supervisora para activar tu acceso."
        )
    if not session.get("vendedor"):
        session_store.set(phone, estado, vendedor=vendedor)

    sup_phone = (config.SUPERVISORA_PHONE or "").lstrip("+")
    es_supervisor = phone.removeprefix("whatsapp:").lstrip("+") == sup_phone
    nombre = vendedor.get("Nombre", "")
    logger.info("procesar() → vendedor=%r  es_supervisor=%s", nombre, es_supervisor)

    # ── Navegación global ────────────────────────────────────────────────────
    if t == "hola":
        session_store.clear(phone)
        session_store.set(phone, ELEGIR_EMPRESA, vendedor=vendedor)
        return _selector_empresa(nombre)

    if t in ("000", "cancelar"):
        session_store.set(phone, ELEGIR_EMPRESA, vendedor=vendedor)
        return _selector_empresa(nombre)

    if t == "cancelar pedido":
        return _iniciar_cancelar_pedido(phone, vendedor)

    if t == "anular pago" and es_supervisor:
        return _iniciar_anular_pago(phone, vendedor)

    if t in ("00", "menu", "menú"):
        empresa = session.get("empresa") or ""
        if not empresa:
            session_store.set(phone, ELEGIR_EMPRESA, vendedor=vendedor)
            return _selector_empresa(nombre)
        session_store.set(phone, MENU, vendedor=vendedor)
        return _menu_texto(empresa, es_supervisor)

    # ── Sin empresa elegida ───────────────────────────────────────────────────
    if not session.get("empresa") and estado != ELEGIR_EMPRESA:
        session_store.set(phone, ELEGIR_EMPRESA, vendedor=vendedor)
        return _selector_empresa(nombre)

    handlers = {
        ELEGIR_EMPRESA:  lambda: _handle_elegir_empresa(phone, t, vendedor, es_supervisor),
        MENU:            lambda: _handle_menu(phone, t, texto, vendedor, es_supervisor),
        PEDIDO_CATEGORIA:lambda: _handle_pedido_categoria(phone, t, texto, vendedor, es_supervisor),
        PEDIDO_PRODUCTOS:lambda: _handle_pedido_productos(phone, t, texto, vendedor),
        PEDIDO_CANTIDAD: lambda: _handle_pedido_cantidad(phone, t, texto, vendedor),
        PEDIDO_CONFIRMAR:lambda: _handle_pedido_confirmar(phone, t, texto, vendedor),
        PAGO_MONTO:      lambda: _handle_pago_monto(phone, texto, vendedor),
        PAGO_METODO:     lambda: _handle_pago_metodo(phone, t, vendedor),
        PAGO_COMPROBANTE:lambda: _handle_pago_comprobante(phone, texto, media_url, vendedor),
        PAGO_CONFIRMAR:  lambda: _handle_pago_confirmar(phone, t, vendedor),
        BAJA_CONFIRMAR:         lambda: _handle_baja_confirmar(phone, t, vendedor),
        CONSULTA_IA:            lambda: _handle_consulta_ia(phone, texto, vendedor),
        POST_ACCION:            lambda: _handle_post_accion(phone, t, vendedor, es_supervisor),
        SUPER_CANDIDATAS:            lambda: _handle_super_candidatas(phone, texto, vendedor),
        CANCELAR_PEDIDO:             lambda: _handle_cancelar_pedido(phone, t, vendedor),
        CANCELAR_PEDIDO_CONFIRM:     lambda: _handle_cancelar_pedido_confirm(phone, t, vendedor),
        ANULAR_PAGO:                 lambda: _handle_anular_pago(phone, t, vendedor),
        ANULAR_PAGO_CONFIRM:         lambda: _handle_anular_pago_confirm(phone, t, vendedor),
        SUPER_MENU:                  lambda: _handle_super_menu(phone, t, vendedor),
        SUPER_CONFIRMAR_PAGO:        lambda: _handle_super_confirmar_pago(phone, texto, vendedor),
        SUPER_CONFIRMAR_PAGO_CONFIRM:lambda: _handle_super_confirmar_pago_confirm(phone, t, vendedor),
    }

    handler = handlers.get(estado)
    if handler is None:
        empresa = session.get("empresa", "CUBO")
        session_store.set(phone, MENU, vendedor=vendedor)
        return _menu_texto(empresa, es_supervisor)
    return handler()


# ── Elegir empresa ────────────────────────────────────────────────────────────

def _handle_elegir_empresa(phone: str, t: str, vendedor: dict, es_supervisor: bool) -> str:
    if t == "1":
        empresa = "CUBO"
    elif t == "2":
        empresa = "CRAFT"
    else:
        return _selector_empresa(vendedor.get("Nombre", ""))
    session_store.set(phone, MENU, vendedor=vendedor, empresa=empresa)
    return f"Hola {vendedor.get('Nombre','')}! 👋\n\n{_menu_texto(empresa, es_supervisor)}"


# ── Menú ──────────────────────────────────────────────────────────────────────

def _handle_menu(
    phone: str,
    t: str,
    texto_original: str,
    vendedor: dict,
    es_supervisor: bool,
) -> str:
    session = session_store.get(phone)
    empresa = session.get("empresa", "CUBO")

    if not t:
        return f"Hola {vendedor.get('Nombre','')}! 👋\n\n{_menu_texto(empresa, es_supervisor)}"

    if _es_pregunta_abierta(texto_original):
        respuesta = procesar_consulta_ia(texto_original, empresa)
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return f"🤖 {respuesta}" + _post_prompt()

    if t == "9" and es_supervisor:
        return _iniciar_super_menu(phone, vendedor)

    accion = _MENU_MAP.get(t)
    return _ejecutar_accion(phone, accion, vendedor, empresa, es_supervisor)


def _ejecutar_accion(
    phone: str,
    accion: str | None,
    vendedor: dict,
    empresa: str,
    es_supervisor: bool,
) -> str:
    if accion == "catalogo":
        session_store.set(phone, PEDIDO_CATEGORIA, vendedor=vendedor, carrito=[])
        return _render_categorias(empresa, [])

    if accion == "pago":
        session_store.set(phone, PAGO_MONTO, vendedor=vendedor)
        return "💰 *Registrar pago*\nIngresá el monto:"

    if accion == "saldo":
        balance = sheets_client.get_balance_vendedor(vendedor)
        deuda = balance["deuda_real"]
        disponible = balance["disponible"]
        pagos_pend = balance["pagos_pendientes"]
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        msg = f"📊 *Tu situación actual:*\nDeuda: *${deuda:.2f}*\nCrédito disponible: ${disponible:.2f}"
        if pagos_pend > 0:
            msg += f"\n_(Pagos en revisión: ${pagos_pend:.2f})_"
        return msg + _post_prompt()

    if accion == "mis_pedidos":
        pedidos = sheets_client.get_ultimos_pedidos(vendedor, limite=5)
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        if not pedidos:
            return "No tenés pedidos registrados." + _post_prompt()
        lines = ["📋 *Tus últimos pedidos:*\n"]
        for p in pedidos:
            lines.append(
                f"• {p.get('ID_Pedido','?')} | {p.get('Nombre_Producto','?')} "
                f"x{p.get('Cantidad','?')} | ${p.get('Total','?')} | {p.get('Estado','?')}"
            )
        return "\n".join(lines) + _post_prompt()

    if accion == "ranking":
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        ranking = sheets_client.calcular_ranking_empresa(empresa)
        if not ranking:
            return f"No hay pedidos de {empresa} registrados este mes aún." + _post_prompt()
        now = datetime.now()
        mes_es = sheets_client._MESES_ES.get(now.month, str(now.month))
        lines = [f"🏆 *Ranking {empresa} — {mes_es} {now.year}*\n"]
        emojis = {1: "🥇", 2: "🥈", 3: "🥉"}
        vid_actual = str(vendedor.get("ID", ""))
        for r in ranking:
            emoji = emojis.get(r["Posición"], f"#{r['Posición']}")
            marker = " ← vos" if r["ID_Vendedor"] == vid_actual else ""
            lines.append(
                f"{emoji} {r['Nombre']} — ${r['Total_Mes']:,.2f} ({r['Categoría']}){marker}"
            )
        return "\n".join(lines) + _post_prompt()

    if accion == "ia":
        session_store.set(phone, CONSULTA_IA, vendedor=vendedor)
        return (
            "🤖 *Asistente Técnico CUBOCRAFT*\n"
            "Escribí tu consulta técnica y te respondo al toque.\n\n"
            "Ejemplos:\n"
            "- ¿Qué casco usar en trabajos eléctricos?\n"
            "- ¿Cuántos bolsones de cemento para 20m²?\n"
            "- ¿Cómo impermeabilizar una terraza?"
        )

    if accion == "supervisor":
        nombre = vendedor.get("Nombre", "?")
        tel = vendedor.get("Teléfono", "?")
        whatsapp_client.notificar_supervisora(
            f"📣 {nombre} ({tel}) quiere hablar con el supervisor."
        )
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return "✅ Le avisé al supervisor. Te va a contactar pronto." + _post_prompt()

    if accion == "baja":
        session_store.set(phone, BAJA_CONFIRMAR, vendedor=vendedor)
        return "⚠️ ¿Confirmás que querés solicitar la baja o pausa? (SI / NO)"

    session_store.set(phone, MENU, vendedor=vendedor)
    return "Opción no reconocida.\n\n" + _menu_texto(empresa, es_supervisor)


# ── Panel supervisor ──────────────────────────────────────────────────────────

def _iniciar_super_menu(phone: str, vendedor: dict) -> str:
    session_store.set(phone, SUPER_MENU, vendedor=vendedor)
    return (
        "👥 *Panel Supervisor* 🔒\n\n"
        "A. Ver candidatas pendientes\n"
        "B. Confirmar / rechazar pagos\n\n"
        "Escribí A o B"
    )


def _handle_super_menu(phone: str, t: str, vendedor: dict) -> str:
    if t == "a":
        return _iniciar_super_candidatas(phone, vendedor)
    if t == "b":
        return _iniciar_confirmar_pagos(phone, vendedor)
    return (
        "Escribí A para candidatas o B para pagos pendientes.\n\n"
        "👥 *Panel Supervisor* 🔒\n"
        "A. Ver candidatas pendientes\n"
        "B. Confirmar / rechazar pagos"
    )


def _iniciar_super_candidatas(phone: str, vendedor: dict) -> str:
    candidatas = sheets_client.get_candidatas_pendientes()
    session_store.set(phone, SUPER_CANDIDATAS, vendedor=vendedor, candidatas=candidatas)
    if not candidatas:
        return "No hay candidatas pendientes." + _post_prompt()
    lines = ["👥 *Candidatas pendientes:*\n"]
    for i, c in enumerate(candidatas, 1):
        lines.append(f"{i}. {c.get('Nombre','?')} — {c.get('Teléfono','?')} ({c.get('Zona','')})")
    lines.append("\n*A<n>* para aprobar  |  *R<n>* para rechazar  (ej: A1 · R2)")
    return "\n".join(lines)


def _handle_super_candidatas(phone: str, texto: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    candidatas: list[dict] = session.get("candidatas", [])
    t = texto.strip().upper()

    if len(t) < 2 or t[0] not in ("A", "R"):
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return "Usá A<n> o R<n> (ej: A1, R2)." + _post_prompt()

    try:
        idx = int(t[1:]) - 1
        candidata = candidatas[idx]
    except (ValueError, IndexError):
        return f"Número inválido. Hay {len(candidatas)} candidata/s listada/s."

    fila: int | None = candidata.get("_row")

    if t[0] == "A":
        nueva_id = sheets_client.pasar_candidata_a_vendedoras(candidata)
        if fila:
            sheets_client.actualizar_candidata(fila, "APROBADA", f"Alta: {nueva_id}")
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        whatsapp_client.notificar_supervisora(
            f"✅ Candidata aprobada: {candidata.get('Nombre','?')} → ID {nueva_id}"
        )
        return f"✅ {candidata.get('Nombre','?')} aprobada — ID: {nueva_id}" + _post_prompt()
    else:
        if fila:
            sheets_client.actualizar_candidata(fila, "RECHAZADA", "")
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return f"❌ {candidata.get('Nombre','?')} rechazada." + _post_prompt()


# ── Flujo PEDIDO ──────────────────────────────────────────────────────────────

def _handle_pedido_categoria(
    phone: str,
    t: str,
    texto: str,
    vendedor: dict,
    es_supervisor: bool,
) -> str:
    session = session_store.get(phone)
    empresa = session.get("empresa", "CUBO")
    carrito = session.get("carrito", [])
    categorias = _CATEGORIAS.get(empresa, [])

    if texto.strip().upper() == "LISTO":
        return _cerrar_pedido(phone, vendedor, session)

    if t == "0":
        session_store.set(phone, MENU, vendedor=vendedor)
        return _menu_texto(empresa, es_supervisor)

    try:
        idx = int(t) - 1
        if idx < 0 or idx >= len(categorias):
            raise ValueError
    except (ValueError, TypeError):
        return _render_categorias(empresa, carrito)

    clave, nombre_display = categorias[idx]
    session_store.set(phone, PEDIDO_PRODUCTOS, vendedor=vendedor,
                      categoria_clave=clave,
                      categoria_nombre=nombre_display)
    return _render_productos(clave, nombre_display, empresa)


def _handle_pedido_productos(phone: str, t: str, texto: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    empresa = session.get("empresa", "CUBO")
    clave = session.get("categoria_clave", "")
    nombre_display = session.get("categoria_nombre", "")
    carrito = session.get("carrito", [])

    if texto.strip().upper() == "LISTO":
        return _cerrar_pedido(phone, vendedor, session)

    if t == "0":
        session_store.set(phone, PEDIDO_CATEGORIA, vendedor=vendedor)
        return _render_categorias(empresa, carrito)

    productos = sheets_client.get_productos_por_categoria(clave, empresa)
    try:
        idx = int(t) - 1
        if idx < 0 or idx >= len(productos):
            raise ValueError
    except (ValueError, TypeError):
        return _render_productos(clave, nombre_display, empresa)

    producto = productos[idx]
    session_store.set(phone, PEDIDO_CANTIDAD, vendedor=vendedor,
                      producto_seleccionado=producto)
    return (
        f"*{producto.get('Nombre','?')}* — ${producto.get('Precio_Vendedor','?')}/u\n\n"
        "¿Cuántas unidades?\n\n"
        "0 para volver a productos"
    )


def _handle_pedido_cantidad(phone: str, t: str, texto: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    empresa = session.get("empresa", "CUBO")
    clave = session.get("categoria_clave", "")
    nombre_display = session.get("categoria_nombre", "")
    carrito = session.get("carrito", [])

    if texto.strip().upper() == "LISTO":
        return _cerrar_pedido(phone, vendedor, session)

    if t == "0":
        session_store.set(phone, PEDIDO_PRODUCTOS, vendedor=vendedor)
        return _render_productos(clave, nombre_display, empresa)

    try:
        cantidad = int(t)
        if cantidad <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return "Ingresá un número entero positivo (ej: 3) o 0 para volver."

    producto = session.get("producto_seleccionado", {})
    precio = float(producto.get("Precio_Vendedor", 0))
    subtotal = precio * cantidad
    campana, desc_pct, total_desc = sheets_client.aplicar_mejor_descuento(vendedor, subtotal)

    total_item = total_desc if (campana and desc_pct > 0) else subtotal
    desc_txt = f" (con {desc_pct:.0f}% dto.)" if (campana and desc_pct > 0) else ""

    session_store.set(phone, PEDIDO_CONFIRMAR, vendedor=vendedor,
                      carrito=carrito,
                      cantidad_seleccionada=cantidad,
                      campana_seleccionada=campana,
                      descuento_seleccionado=desc_pct)
    return (
        f"• *{producto.get('Nombre','?')}* x{cantidad} = ${total_item:.0f}{desc_txt}\n\n"
        "SI para agregar / NO para descartar"
    )


def _handle_pedido_confirmar(phone: str, t: str, texto: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    empresa = session.get("empresa", "CUBO")
    clave = session.get("categoria_clave", "")
    nombre_display = session.get("categoria_nombre", "")
    carrito = list(session.get("carrito", []))

    if texto.strip().upper() == "LISTO":
        return _cerrar_pedido(phone, vendedor, session)

    if t in ("si", "sí"):
        producto = session.get("producto_seleccionado", {})
        carrito.append({
            "producto": producto,
            "cantidad": session.get("cantidad_seleccionada", 1),
            "descuento_pct": session.get("descuento_seleccionado", 0),
            "campana": session.get("campana_seleccionada"),
        })
        session_store.set(phone, PEDIDO_CATEGORIA, vendedor=vendedor,
                          carrito=carrito, producto_seleccionado=None)
        return _render_categorias(empresa, carrito)

    if t == "no" or t == "0":
        session_store.set(phone, PEDIDO_PRODUCTOS, vendedor=vendedor, carrito=carrito)
        return _render_productos(clave, nombre_display, empresa)

    return "SI para agregar al carrito / NO para descartar / LISTO para cerrar el pedido"


def _cerrar_pedido(phone: str, vendedor: dict, session: dict) -> str:
    carrito: list = session.get("carrito", [])
    if not carrito:
        empresa = session.get("empresa", "CUBO")
        session_store.set(phone, PEDIDO_CATEGORIA, vendedor=vendedor, carrito=[])
        return "El carrito está vacío.\n\n" + _render_categorias(empresa, [])

    ids_registrados = []
    for item in carrito:
        campana_id = (item.get("campana") or {}).get("ID", "")
        pid = sheets_client.registrar_pedido(
            vendedor, item["producto"], item["cantidad"],
            item.get("descuento_pct", 0), campana_id,
        )
        ids_registrados.append(pid)

    resumen = "\n".join(
        f"  • {i['producto'].get('Nombre','?')} x{i['cantidad']}" for i in carrito
    )
    session_store.set(phone, POST_ACCION, vendedor=vendedor)
    whatsapp_client.notificar_supervisora(
        f"🛒 Pedido de {vendedor.get('Nombre','?')} ({vendedor.get('Teléfono','?')}):\n{resumen}"
    )
    return (
        "🎉 *Pedido registrado!*\n"
        f"IDs: {', '.join(ids_registrados)}\n\n"
        f"Resumen:\n{resumen}"
        + _post_prompt()
    )


# ── Flujo PAGO ────────────────────────────────────────────────────────────────

def _handle_pago_monto(phone: str, texto: str, vendedor: dict) -> str:
    try:
        monto = float(texto.replace(",", ".").replace("$", "").strip())
        if monto <= 0:
            raise ValueError
    except ValueError:
        return "Ingresá un monto válido (ej: 5000 o 1500.50)."
    session_store.set(phone, PAGO_METODO, vendedor=vendedor, pago_monto=monto)
    return (
        f"Monto: *${monto:.2f}*\n\n"
        "💳 *Método de pago:*\n"
        "1️⃣ Transferencia bancaria\n"
        "2️⃣ Efectivo\n"
        "3️⃣ MercadoPago"
    )


def _handle_pago_metodo(phone: str, t: str, vendedor: dict) -> str:
    if t not in ("1", "2", "3"):
        return "Elegí 1, 2 o 3."
    metodo = sheets_client.METODOS[t]
    session = session_store.get(phone)
    session_store.set(phone, PAGO_COMPROBANTE, vendedor=vendedor,
                      pago_monto=session.get("pago_monto"),
                      pago_metodo=metodo)
    return f"Método: *{metodo}*\n\nAdjuntá el comprobante (imagen o número de referencia):"


def _handle_pago_comprobante(
    phone: str,
    texto: str,
    media_url: str | None,
    vendedor: dict,
) -> str:
    if not texto and not media_url:
        return "Adjuntá el comprobante (imagen o texto con el número de referencia)."

    session = session_store.get(phone)
    comprobante = texto or ""

    if media_url:
        es_valido, ocr_texto = whatsapp_client.validar_comprobante_imagen(media_url)
        comprobante = ocr_texto or media_url
        if not es_valido:
            logger.warning("Posible comprobante inválido de %s", phone)

    monto = float(session.get("pago_monto") or 0)
    metodo = session.get("pago_metodo") or "?"

    session_store.set(phone, PAGO_CONFIRMAR, vendedor=vendedor,
                      pago_monto=monto,
                      pago_metodo=metodo,
                      pago_comprobante=comprobante)
    return (
        "📄 *Confirmar pago:*\n"
        f"Monto: ${monto:.2f}\n"
        f"Método: {metodo}\n\n"
        "¿Confirmás? (SI / NO)"
    )


def _handle_pago_confirmar(phone: str, t: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    if t in ("si", "sí"):
        monto = float(session.get("pago_monto") or 0)
        metodo = session.get("pago_metodo") or ""
        comprobante = session.get("pago_comprobante") or ""
        pid, _, _ = sheets_client.registrar_pago(vendedor, monto, metodo, comprobante)
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        whatsapp_client.notificar_supervisora(
            f"💰 Pago pendiente de confirmación\n"
            f"Vendedor: {vendedor.get('Nombre','?')} | ${monto:.2f} via {metodo} | ID: {pid}\n"
            f"Panel supervisor (9) → B para confirmar o rechazar"
        )
        return (
            f"✅ *Pago enviado para revisión.*\nID: {pid}\nMonto: ${monto:.2f}\n"
            "El supervisor lo confirmará en breve."
            + _post_prompt()
        )
    if t == "no":
        session_store.set(phone, MENU, vendedor=vendedor)
        return "Pago cancelado."
    return "Respondé SI o NO."


# ── Baja ──────────────────────────────────────────────────────────────────────

def _handle_baja_confirmar(phone: str, t: str, vendedor: dict) -> str:
    if t in ("si", "sí"):
        session_store.clear(phone)
        whatsapp_client.notificar_supervisora(
            f"⚠️ Solicitud de baja: {vendedor.get('Nombre','?')} ({vendedor.get('Teléfono','?')})"
        )
        return "Tu solicitud fue enviada a la supervisora. Nos contactaremos pronto. ¡Gracias! 👋"
    if t == "no":
        session_store.set(phone, MENU, vendedor=vendedor)
        return "Baja cancelada. Volvés al menú."
    return "Respondé SI o NO."


# ── Consulta IA ───────────────────────────────────────────────────────────────

def _handle_consulta_ia(phone: str, texto: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    empresa = session.get("empresa", "CUBO")
    if not texto:
        return "¿Cuál es tu consulta técnica?"
    respuesta = procesar_consulta_ia(texto, empresa)
    session_store.set(phone, POST_ACCION, vendedor=vendedor)
    return f"🤖 {respuesta}" + _post_prompt()


# ── Post acción ───────────────────────────────────────────────────────────────

def _handle_post_accion(phone: str, t: str, vendedor: dict, es_supervisor: bool) -> str:
    session = session_store.get(phone)
    empresa = session.get("empresa", "CUBO")
    if t == "1":
        session_store.set(phone, MENU, vendedor=vendedor)
        return _menu_texto(empresa, es_supervisor)
    if t == "2":
        session_store.clear(phone)
        return f"¡Hasta pronto, {vendedor.get('Nombre', '')}! 👋"
    return "1️⃣ Volver al menú  |  2️⃣ Hasta pronto 👋"


# ── Cancelar pedido ───────────────────────────────────────────────────────────

def _iniciar_cancelar_pedido(phone: str, vendedor: dict) -> str:
    pendientes = sheets_client.get_pedidos_pendientes(vendedor)
    session_store.set(phone, CANCELAR_PEDIDO, vendedor=vendedor, pedidos_cancelables=pendientes)
    if not pendientes:
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return "No tenés pedidos pendientes para cancelar." + _post_prompt()
    lines = ["📋 *Tus pedidos pendientes:*\n"]
    for i, p in enumerate(pendientes, 1):
        lines.append(
            f"{i}. {p.get('ID_Pedido','?')} — {p.get('Nombre_Producto','?')} "
            f"x{p.get('Cantidad','?')} — ${p.get('Total','?')}"
        )
    lines.append("\nEscribí el número para cancelar, o 00 para volver al menú.")
    return "\n".join(lines)


def _handle_cancelar_pedido(phone: str, t: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    pendientes: list[dict] = session.get("pedidos_cancelables", [])
    try:
        idx = int(t) - 1
        if idx < 0 or idx >= len(pendientes):
            raise ValueError
    except (ValueError, TypeError):
        return f"Elegí un número del 1 al {len(pendientes)}, o 00 para volver."
    pedido = pendientes[idx]
    session_store.set(phone, CANCELAR_PEDIDO_CONFIRM, vendedor=vendedor,
                      pedido_a_cancelar=pedido)
    return (
        f"¿Cancelar *{pedido.get('ID_Pedido','?')}* — "
        f"{pedido.get('Nombre_Producto','?')} x{pedido.get('Cantidad','?')} "
        f"por ${pedido.get('Total','?')}?\n\n"
        "Esta acción no se puede deshacer. (SI / NO)"
    )


def _handle_cancelar_pedido_confirm(phone: str, t: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    pedido = session.get("pedido_a_cancelar", {})
    if t in ("si", "sí"):
        ok = sheets_client.cancelar_pedido(
            str(pedido.get("ID_Pedido", "")),
            str(vendedor.get("ID", "")),
        )
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        if ok:
            whatsapp_client.notificar_supervisora(
                f"🚫 Pedido cancelado: {pedido.get('ID_Pedido','?')} "
                f"de {vendedor.get('Nombre','?')} — {pedido.get('Nombre_Producto','?')}"
            )
            return f"✅ Pedido {pedido.get('ID_Pedido','?')} cancelado." + _post_prompt()
        return "No se pudo cancelar el pedido. Puede que ya no esté pendiente." + _post_prompt()
    if t == "no":
        return _iniciar_cancelar_pedido(phone, vendedor)
    return "Respondé SI o NO."


# ── Anular pago (supervisor) ──────────────────────────────────────────────────

def _iniciar_anular_pago(phone: str, vendedor: dict) -> str:
    pagos = sheets_client.get_pagos_confirmados_todos()
    session_store.set(phone, ANULAR_PAGO, vendedor=vendedor, pagos_anulables=pagos)
    if not pagos:
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return "No hay pagos confirmados para anular." + _post_prompt()
    lines = ["💰 *Pagos confirmados:*\n"]
    for i, p in enumerate(pagos, 1):
        lines.append(
            f"{i}. {p.get('ID_Pago','?')} — {p.get('Nombre_Vendedor','?')} "
            f"— ${p.get('Monto','?')} — {p.get('Fecha','?')}"
        )
    lines.append("\nEscribí el número para anular, o 00 para volver al menú.")
    return "\n".join(lines)


def _handle_anular_pago(phone: str, t: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    pagos: list[dict] = session.get("pagos_anulables", [])
    try:
        idx = int(t) - 1
        if idx < 0 or idx >= len(pagos):
            raise ValueError
    except (ValueError, TypeError):
        return f"Elegí un número del 1 al {len(pagos)}, o 00 para volver."
    pago = pagos[idx]
    session_store.set(phone, ANULAR_PAGO_CONFIRM, vendedor=vendedor,
                      pago_a_anular=pago)
    return (
        f"¿Anular *{pago.get('ID_Pago','?')}* — "
        f"{pago.get('Nombre_Vendedor','?')} — ${pago.get('Monto','?')} "
        f"del {pago.get('Fecha','?')}?\n\n"
        "Esta acción no se puede deshacer. (SI / NO)"
    )


def _handle_anular_pago_confirm(phone: str, t: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    pago = session.get("pago_a_anular", {})
    if t in ("si", "sí"):
        ok = sheets_client.anular_pago(str(pago.get("ID_Pago", "")))
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        if ok:
            whatsapp_client.notificar_supervisora(
                f"🚫 Pago anulado: {pago.get('ID_Pago','?')} "
                f"de {pago.get('Nombre_Vendedor','?')} — ${pago.get('Monto','?')}"
            )
            return (
                f"✅ Pago {pago.get('ID_Pago','?')} anulado. "
                "El saldo del vendedor se actualizará automáticamente."
                + _post_prompt()
            )
        return "No se pudo anular el pago." + _post_prompt()
    if t == "no":
        return _iniciar_anular_pago(phone, vendedor)
    return "Respondé SI o NO."


# ── Confirmar / rechazar pagos pendientes (supervisor) ────────────────────────

def _iniciar_confirmar_pagos(phone: str, vendedor: dict) -> str:
    pagos = sheets_client.get_pagos_pendientes_todos()
    session_store.set(phone, SUPER_CONFIRMAR_PAGO, vendedor=vendedor, pagos_pendientes=pagos)
    if not pagos:
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return "No hay pagos pendientes de confirmación." + _post_prompt()
    lines = ["💰 *Pagos pendientes de confirmación:*\n"]
    for i, p in enumerate(pagos, 1):
        lines.append(
            f"{i}. {p.get('ID_Pago','?')} — {p.get('Nombre_Vendedor','?')} "
            f"— ${p.get('Monto','?')} via {p.get('Metodo','?')} — {p.get('Fecha','?')}"
        )
    lines.append("\n*C<n>* para confirmar | *R<n>* para rechazar  (ej: C1 · R2)")
    return "\n".join(lines)


def _handle_super_confirmar_pago(phone: str, texto: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    pagos: list[dict] = session.get("pagos_pendientes", [])
    t = texto.strip().upper()

    if len(t) < 2 or t[0] not in ("C", "R"):
        return f"Usá C<n> para confirmar o R<n> para rechazar (ej: C1, R2). Hay {len(pagos)} pago(s)."

    try:
        idx = int(t[1:]) - 1
        pago = pagos[idx]
    except (ValueError, IndexError):
        return f"Número inválido. Hay {len(pagos)} pago(s) listado(s)."

    accion = t[0]
    accion_txt = "confirmar" if accion == "C" else "rechazar"
    session_store.set(phone, SUPER_CONFIRMAR_PAGO_CONFIRM, vendedor=vendedor,
                      pago_a_gestionar=pago, accion_pago=accion)
    return (
        f"¿{accion_txt.capitalize()} *{pago.get('ID_Pago','?')}* de "
        f"{pago.get('Nombre_Vendedor','?')} por ${pago.get('Monto','?')}?\n\n"
        "Esta acción no se puede deshacer. (SI / NO)"
    )


def _handle_super_confirmar_pago_confirm(phone: str, t: str, vendedor: dict) -> str:
    session = session_store.get(phone)
    pago = session.get("pago_a_gestionar", {})
    accion = session.get("accion_pago", "C")
    id_pago = str(pago.get("ID_Pago", ""))
    id_vendedor_pago = str(pago.get("ID_Vendedor", ""))

    if t in ("si", "sí"):
        if accion == "C":
            ok = sheets_client.confirmar_pago(id_pago)
            msg_sup = f"✅ Pago {id_pago} confirmado."
            msg_vendedor = f"✅ Tu pago {id_pago} de ${pago.get('Monto','?')} fue confirmado. ¡Gracias!"
        else:
            ok = sheets_client.anular_pago(id_pago)
            msg_sup = f"❌ Pago {id_pago} rechazado (→ ANULADO)."
            msg_vendedor = (
                f"❌ Tu pago {id_pago} de ${pago.get('Monto','?')} fue rechazado. "
                "Contactá al supervisor."
            )

        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        if ok:
            vendedor_data = sheets_client.get_vendedor_by_id(id_vendedor_pago)
            if vendedor_data:
                phone_vendedor = str(vendedor_data.get("Teléfono", ""))
                if phone_vendedor:
                    whatsapp_client.enviar(phone_vendedor, msg_vendedor)
            return msg_sup + _post_prompt()
        return "No se pudo procesar el pago. Puede que ya no esté pendiente." + _post_prompt()

    if t == "no":
        return _iniciar_confirmar_pagos(phone, vendedor)
    return "Respondé SI o NO."
