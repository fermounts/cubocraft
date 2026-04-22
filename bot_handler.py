import logging

import anthropic

import config
import session_store
import sheets_client
import whatsapp_client

logger = logging.getLogger(__name__)

# ── Estados ───────────────────────────────────────────────────────────────────
MENU = "MENU"
PEDIDO_CATALOGO = "PEDIDO_CATALOGO"
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

# ── Mapas de menú por perfil ──────────────────────────────────────────────────
_MENU_MAP: dict[str, dict[str, str]] = {
    "Seguridad": {
        "1": "catalogo_epp",
        "2": "pago",
        "3": "saldo",
        "4": "ranking",
        "5": "ia",
        "6": "baja",
    },
    "Asesor": {
        "1": "calculadora",
        "2": "pago",
        "3": "saldo",
        "4": "ranking",
        "5": "ia",
        "6": "baja",
    },
    "": {
        "1": "catalogo",
        "2": "mis_pedidos",
        "3": "pago",
        "4": "saldo",
        "5": "ranking",
        "6": "ia",
        "7": "baja",
        "8": "ayuda",
    },
}

_MENU_TEXTO: dict[str, str] = {
    "Seguridad": (
        "🏗️ *CUBOCRAFT — EPP & Seguridad*\n"
        "1️⃣ Catálogo EPP\n"
        "2️⃣ Registrar pago\n"
        "3️⃣ Ver saldo\n"
        "4️⃣ Mi ranking\n"
        "5️⃣ Consulta técnica IA\n"
        "6️⃣ Solicitar baja\n"
    ),
    "Asesor": (
        "🏗️ *CUBOCRAFT — Métodos Constructivos*\n"
        "1️⃣ Calculadora de obra\n"
        "2️⃣ Registrar pago\n"
        "3️⃣ Ver saldo\n"
        "4️⃣ Mi ranking\n"
        "5️⃣ Consulta técnica IA\n"
        "6️⃣ Solicitar baja\n"
    ),
    "": (
        "🏗️ *CUBOCRAFT — Menú Principal*\n"
        "1️⃣ Ver catálogo / hacer pedido\n"
        "2️⃣ Ver mis pedidos\n"
        "3️⃣ Registrar pago\n"
        "4️⃣ Ver saldo\n"
        "5️⃣ Mi ranking\n"
        "6️⃣ Consulta técnica IA\n"
        "7️⃣ Solicitar baja\n"
        "8️⃣ Ayuda\n"
    ),
}

_COMANDOS_RESET = {"cancelar", "menu", "menú", "0", "hola"}
_COMANDOS_CONTROL = {"si", "sí", "no", "cancelar", "listo", "fin", "menu", "menú", "hola"}

_ai_client: anthropic.Anthropic | None = None


def _get_ai_client() -> anthropic.Anthropic:
    global _ai_client
    if _ai_client is None:
        _ai_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _ai_client


def _menu_texto(perfil: str, es_supervisor: bool) -> str:
    base = _MENU_TEXTO.get(perfil, _MENU_TEXTO[""])
    return base + ("9️⃣ Panel supervisor\n" if es_supervisor else "")


def _menu_map(perfil: str) -> dict[str, str]:
    return _MENU_MAP.get(perfil, _MENU_MAP[""])


def _post_prompt() -> str:
    return "\n\n1️⃣ Volver al menú  |  2️⃣ Hasta pronto 👋"


def _es_pregunta_abierta(texto: str) -> bool:
    t = texto.strip().lower()
    if not t or t.isdigit():
        return False
    if t in _COMANDOS_CONTROL:
        return False
    # Códigos de producto cortos (ej: P01, EPP3)
    if len(t) <= 6 and t.replace("-", "").replace("_", "").isalnum():
        return False
    return True


def _catalogo_texto(productos: list[dict]) -> str:
    if not productos:
        return "No hay productos disponibles en este momento."
    lines = ["📦 *Catálogo:*\n"]
    for p in productos:
        lines.append(f"• [{p.get('ID','?')}] {p.get('Nombre','?')} — ${p.get('Precio_Vendedor','?')}")
    lines.append("\nEscribí el *ID* del producto para agregarlo al carrito.\nO escribí *LISTO* para cerrar el pedido.")
    return "\n".join(lines)


# ── Consulta IA ───────────────────────────────────────────────────────────────

def procesar_consulta_ia(texto_usuario: str, perfil_vendedor: str) -> str:
    conocimiento = sheets_client.get_conocimiento_tecnico()
    ctx = "\n".join(
        f"TEMA: {k.get('TEMA','')} | NORMA: {k.get('NORMA','')} | CONCEPTO: {k.get('CONCEPTO_CLAVE','')}"
        for k in conocimiento
    ) or "Sin conocimiento técnico cargado."

    system_text = (
        "Sos el Ingeniero Experto de CUBOCRAFT. "
        "Respondés en español, máximo 4-5 líneas (es para WhatsApp). "
        "Citás normativas IRAM, CIRSOC, SRT según corresponda. "
        "Líneas de negocio: EPP (IRAM 3620 cascos, IRAM 3610 calzado, SRT 299/11) "
        "y Métodos Constructivos (CIRSOC 201, IRAM 1597).\n\n"
        f"Conocimiento técnico disponible:\n{ctx}\n\n"
        f"Perfil del usuario: {perfil_vendedor}"
    )
    try:
        resp = _get_ai_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": texto_usuario}],
        )
        return resp.content[0].text
    except anthropic.AuthenticationError:
        logger.error("Anthropic AuthenticationError")
        return "Error de autenticación con IA. Contactá al administrador."
    except anthropic.RateLimitError:
        logger.warning("Anthropic RateLimitError")
        return "Servicio de IA temporalmente no disponible. Intentá en unos minutos."
    except Exception as e:
        logger.error("Error en consulta IA: %s", e)
        return "No pude procesar tu consulta. Intentá de nuevo."


# ── Router principal ──────────────────────────────────────────────────────────

def procesar(phone: str, texto: str, media_url: str | None = None) -> str:
    texto = (texto or "").strip()
    t = texto.lower()

    if t in _COMANDOS_RESET:
        session_store.clear(phone)
        t = ""
        texto = ""

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

    perfil = str(vendedor.get("Perfil", "")).strip()
    sup_phone = (config.SUPERVISORA_PHONE or "").lstrip("+")
    es_supervisor = phone.lstrip("+") == sup_phone

    handlers = {
        MENU:            lambda: _handle_menu(phone, t, texto, vendedor, perfil, es_supervisor),
        PEDIDO_CATALOGO: lambda: _handle_pedido_catalogo(phone, texto, vendedor),
        PEDIDO_CANTIDAD: lambda: _handle_pedido_cantidad(phone, texto, vendedor),
        PEDIDO_CONFIRMAR:lambda: _handle_pedido_confirmar(phone, t, vendedor),
        PAGO_MONTO:      lambda: _handle_pago_monto(phone, texto, vendedor),
        PAGO_METODO:     lambda: _handle_pago_metodo(phone, t, vendedor),
        PAGO_COMPROBANTE:lambda: _handle_pago_comprobante(phone, texto, media_url, vendedor),
        PAGO_CONFIRMAR:  lambda: _handle_pago_confirmar(phone, t, vendedor),
        BAJA_CONFIRMAR:  lambda: _handle_baja_confirmar(phone, t, vendedor),
        CONSULTA_IA:     lambda: _handle_consulta_ia(phone, texto, vendedor, perfil),
        POST_ACCION:     lambda: _handle_post_accion(phone, t, vendedor, perfil, es_supervisor),
        SUPER_CANDIDATAS:lambda: _handle_super_candidatas(phone, texto, vendedor),
    }

    handler = handlers.get(estado)
    if handler is None:
        session_store.set(phone, MENU, vendedor=vendedor)
        return _menu_texto(perfil, es_supervisor)
    return handler()


# ── Menú ──────────────────────────────────────────────────────────────────────

def _handle_menu(
    phone: str,
    t: str,
    texto_original: str,
    vendedor: dict,
    perfil: str,
    es_supervisor: bool,
) -> str:
    if not t:
        session_store.set(phone, MENU, vendedor=vendedor)
        nombre = vendedor.get("Nombre", "")
        return f"Hola {nombre}! 👋\n\n{_menu_texto(perfil, es_supervisor)}"

    if _es_pregunta_abierta(texto_original):
        respuesta = procesar_consulta_ia(texto_original, perfil)
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return f"🤖 {respuesta}" + _post_prompt()

    if t == "9" and es_supervisor:
        return _iniciar_super_candidatas(phone, vendedor)

    accion = _menu_map(perfil).get(t)
    return _ejecutar_accion(phone, accion, vendedor, perfil, es_supervisor)


def _ejecutar_accion(
    phone: str,
    accion: str | None,
    vendedor: dict,
    perfil: str,
    es_supervisor: bool,
) -> str:
    if accion in ("catalogo", "catalogo_epp"):
        productos = sheets_client.get_productos_activos()
        if accion == "catalogo_epp":
            filtrados = [
                p for p in productos
                if "epp" in str(p.get("Categoría", "")).lower()
                or "seguridad" in str(p.get("Categoría", "")).lower()
            ]
            productos = filtrados or productos
        session_store.set(phone, PEDIDO_CATALOGO, vendedor=vendedor, carrito=[])
        return _catalogo_texto(productos)

    if accion == "calculadora":
        session_store.set(phone, MENU, vendedor=vendedor)
        return (
            "🧱 *Calculadora de Obra*\n"
            "Describí el trabajo (ej: 'necesito cubrir 50m² con mortero') "
            "y te ayudo a calcular los materiales y cantidades necesarias."
        )

    if accion == "mis_pedidos":
        pedido = sheets_client.get_ultimo_pedido(vendedor)
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        if pedido:
            return (
                "📋 *Último pedido:*\n"
                f"ID: {pedido.get('ID','?')} | Producto: {pedido.get('Nombre_Producto','?')}\n"
                f"Cantidad: {pedido.get('Cantidad','?')} | Total: ${pedido.get('Subtotal','?')}\n"
                f"Estado: {pedido.get('Estado','?')}"
                + _post_prompt()
            )
        return "No tenés pedidos registrados." + _post_prompt()

    if accion == "pago":
        session_store.set(phone, PAGO_MONTO, vendedor=vendedor)
        return "💰 *Registrar pago*\nIngresá el monto:"

    if accion == "saldo":
        saldo = sheets_client.get_saldo(vendedor)
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return f"💳 Tu saldo acumulado: *${saldo:.2f}*" + _post_prompt()

    if accion == "ranking":
        rank = sheets_client.get_ranking_vendedora(vendedor)
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        if rank:
            return (
                "🏆 *Tu ranking:*\n"
                f"Posición: #{rank.get('Posicion','?')}\n"
                f"Ventas: ${rank.get('Total_Ventas','?')} | Puntos: {rank.get('Puntos','?')}"
                + _post_prompt()
            )
        return "No tenés datos de ranking aún." + _post_prompt()

    if accion == "ia":
        session_store.set(phone, CONSULTA_IA, vendedor=vendedor)
        return "🤖 *Consulta técnica*\n¿Cuál es tu pregunta sobre EPP o construcción?"

    if accion == "baja":
        session_store.set(phone, BAJA_CONFIRMAR, vendedor=vendedor)
        return "⚠️ ¿Confirmás que querés solicitar la baja? (SI / NO)"

    if accion == "ayuda":
        session_store.set(phone, POST_ACCION, vendedor=vendedor)
        return (
            "ℹ️ *Ayuda CUBOCRAFT*\n"
            "• Pedidos: opción 1\n"
            "• Consultas técnicas (EPP, construcción): opción 6\n"
            "• Escribí *menu* en cualquier momento para volver\n"
            "• Podés preguntar directamente sin elegir opción"
            + _post_prompt()
        )

    session_store.set(phone, MENU, vendedor=vendedor)
    return "Opción no reconocida.\n\n" + _menu_texto(perfil, es_supervisor)


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

def _handle_pedido_catalogo(phone: str, texto: str, vendedor: dict) -> str:
    if texto.strip().upper() == "LISTO":
        return _cerrar_pedido(phone, vendedor, session_store.get(phone))

    producto = sheets_client.get_producto_by_id(texto.strip())
    if not producto:
        productos = sheets_client.get_productos_activos()
        return f"ID '{texto}' no encontrado.\n\n" + _catalogo_texto(productos)

    session = session_store.get(phone)
    session_store.set(phone, PEDIDO_CANTIDAD, vendedor=vendedor,
                      carrito=session.get("carrito", []),
                      producto_seleccionado=producto)
    return (
        f"✅ *{producto.get('Nombre','?')}*\n"
        f"Precio: ${producto.get('Precio_Vendedor','?')}\n\n"
        "¿Qué cantidad querés?"
    )


def _handle_pedido_cantidad(phone: str, texto: str, vendedor: dict) -> str:
    try:
        cantidad = int(texto.strip())
        if cantidad <= 0:
            raise ValueError
    except ValueError:
        return "Ingresá un número entero positivo (ej: 3)."

    session = session_store.get(phone)
    producto = session.get("producto_seleccionado", {})
    precio = float(producto.get("Precio_Vendedor", 0))
    subtotal = precio * cantidad
    campana, desc_pct, total_desc = sheets_client.aplicar_mejor_descuento(vendedor, subtotal)

    desc_txt = ""
    if campana and desc_pct > 0:
        ahorro = subtotal - total_desc
        desc_txt = (
            f"\n🎁 Descuento {campana.get('Nombre','')} ({desc_pct:.0f}%): "
            f"-${ahorro:.2f} → Total: ${total_desc:.2f}"
        )

    session_store.set(phone, PEDIDO_CONFIRMAR, vendedor=vendedor,
                      carrito=session.get("carrito", []),
                      producto_seleccionado=producto,
                      cantidad_seleccionada=cantidad,
                      campana_seleccionada=campana,
                      descuento_seleccionado=desc_pct)
    return (
        "📦 *Confirmar item:*\n"
        f"Producto: {producto.get('Nombre','?')}\n"
        f"Cantidad: {cantidad}\n"
        f"Precio unitario: ${precio:.2f}\n"
        f"Subtotal: ${subtotal:.2f}{desc_txt}\n\n"
        "¿Confirmás? (SI / NO · o LISTO para cerrar el pedido)"
    )


def _handle_pedido_confirmar(phone: str, t: str, vendedor: dict) -> str:
    session = session_store.get(phone)

    if t == "listo":
        return _cerrar_pedido(phone, vendedor, session)

    if t in ("si", "sí"):
        carrito: list = list(session.get("carrito", []))
        carrito.append({
            "producto": session.get("producto_seleccionado", {}),
            "cantidad": session.get("cantidad_seleccionada", 1),
            "descuento_pct": session.get("descuento_seleccionado", 0),
            "campana": session.get("campana_seleccionada"),
        })
        session_store.set(phone, PEDIDO_CATALOGO, vendedor=vendedor,
                          carrito=carrito, producto_seleccionado=None)
        resumen = "\n".join(
            f"  • {i['producto'].get('Nombre','?')} x{i['cantidad']}" for i in carrito
        )
        productos = sheets_client.get_productos_activos()
        return (
            f"✅ Agregado al carrito ({len(carrito)} item/s):\n{resumen}\n\n"
            + _catalogo_texto(productos)
        )

    if t == "no":
        session_store.set(phone, PEDIDO_CATALOGO, vendedor=vendedor,
                          carrito=session.get("carrito", []))
        return "Item cancelado.\n\n" + _catalogo_texto(sheets_client.get_productos_activos())

    return "Respondé SI, NO o LISTO."


def _cerrar_pedido(phone: str, vendedor: dict, session: dict) -> str:
    carrito: list = session.get("carrito", [])
    if not carrito:
        session_store.set(phone, MENU, vendedor=vendedor)
        return "El carrito está vacío."

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

def _handle_consulta_ia(phone: str, texto: str, vendedor: dict, perfil: str) -> str:
    if not texto:
        return "¿Cuál es tu consulta técnica?"
    respuesta = procesar_consulta_ia(texto, perfil)
    session_store.set(phone, POST_ACCION, vendedor=vendedor)
    return f"🤖 {respuesta}" + _post_prompt()


# ── Post acción ───────────────────────────────────────────────────────────────

def _handle_post_accion(
    phone: str,
    t: str,
    vendedor: dict,
    perfil: str,
    es_supervisor: bool,
) -> str:
    if t == "1":
        session_store.set(phone, MENU, vendedor=vendedor)
        return _menu_texto(perfil, es_supervisor)
    if t == "2":
        session_store.clear(phone)
        return f"¡Hasta pronto, {vendedor.get('Nombre', '')}! 👋"
    return "1️⃣ Volver al menú  |  2️⃣ Hasta pronto 👋"
