import logging

from google import genai
from google.genai import types as genai_types

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

_gemini_client: genai.Client | None = None


def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _gemini_client


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


# ── Consulta IA ───────────────────────────────────────────────────────────────

def procesar_consulta_ia(texto_usuario: str, empresa: str) -> str:
    conocimiento = sheets_client.get_conocimiento_tecnico()
    ctx = "\n".join(
        f"ID: {k.get('ID_Norma','')} | NORMA: {k.get('Nombre_Norma','')} | ALCANCE: {k.get('Alcance','')}"
        for k in conocimiento
    ) or "Sin conocimiento técnico cargado."

    linea = (
        "EPP (IRAM 3620 cascos, IRAM 3627 calzado, IRAM 3649 guantes, SRT 299/11)"
        if empresa == "CUBO"
        else "Métodos Constructivos (CIRSOC 201, IRAM 1597)"
    )
    system_text = (
        "Sos el Ingeniero Experto de CUBOCRAFT. "
        "Respondés en español, máximo 4-5 líneas (es para WhatsApp). "
        "Citás normativas IRAM, CIRSOC, SRT según corresponda. "
        f"Línea de negocio activa: {linea}.\n\n"
        f"Conocimiento técnico disponible:\n{ctx}"
    )
    try:
        resp = _get_gemini_client().models.generate_content(
            model="gemini-1.5-flash",
            contents=texto_usuario,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_text,
                max_output_tokens=300,
            ),
        )
        return resp.text
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in ("api key", "authentication", "permission denied", "unauthenticated")):
            logger.error("Gemini auth error: %s", e)
            return "Error de autenticación con IA. Contactá al administrador."
        if any(k in msg for k in ("quota", "resource exhausted", "rate limit")):
            logger.warning("Gemini rate limit: %s", e)
            return "Servicio de IA temporalmente no disponible. Intentá en unos minutos."
        logger.error("Error en consulta IA: %s", e)
        return "No pude procesar tu consulta. Intentá de nuevo."


# ── Router principal ──────────────────────────────────────────────────────────

def procesar(phone: str, texto: str, media_url: str | None = None) -> str:
    logger.info("procesar() → phone=%r  texto=%r", phone, texto)
    texto = (texto or "").strip()
    t = texto.lower()

    session = session_store.get(phone)
    estado = session.get("estado", MENU)

    vendedor = session.get("vendedor") or sheets_client.get_vendedora_by_phone(phone)
    if not vendedor:
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

    # ── Navegación global ────────────────────────────────────────────────────
    if t == "hola":
        session_store.clear(phone)
        session_store.set(phone, ELEGIR_EMPRESA, vendedor=vendedor)
        return _selector_empresa(nombre)

    if t in ("000", "cancelar"):
        session_store.set(phone, ELEGIR_EMPRESA, vendedor=vendedor)
        return _selector_empresa(nombre)

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
        BAJA_CONFIRMAR:  lambda: _handle_baja_confirmar(phone, t, vendedor),
        CONSULTA_IA:     lambda: _handle_consulta_ia(phone, texto, vendedor),
        POST_ACCION:     lambda: _handle_post_accion(phone, t, vendedor, es_supervisor),
        SUPER_CANDIDATAS:lambda: _handle_super_candidatas(phone, texto, vendedor),
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
        return _iniciar_super_candidatas(phone, vendedor)

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
        saldo = sheets_client.get_saldo(vendedor)
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return f"💳 Tu saldo acumulado: *${saldo:.2f}*" + _post_prompt()

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
        rank = sheets_client.get_ranking_vendedora(vendedor)
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        if rank:
            return (
                "🏆 *Tu ranking:*\n"
                f"Posición: #{rank.get('Posición_Semana','?')}\n"
                f"Categoría: {rank.get('Categoría','?')}\n"
                f"Ventas semana: ${rank.get('Ventas_Semana','?')} | Mes: ${rank.get('Ventas_Mes','?')}"
                + _post_prompt()
            )
        return "No tenés datos de ranking aún." + _post_prompt()

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
        pid, _, nuevo_saldo = sheets_client.registrar_pago(vendedor, monto, metodo, comprobante)
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        whatsapp_client.notificar_supervisora(
            f"💰 Pago de {vendedor.get('Nombre','?')}: ${monto:.2f} via {metodo} | ID: {pid}"
        )
        return (
            f"✅ *Pago registrado!*\nID: {pid}\n"
            f"Monto: ${monto:.2f}\nNuevo saldo: ${nuevo_saldo:.2f}"
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
