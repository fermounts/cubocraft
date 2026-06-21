# CONTEXTO PROYECTO CUBOCRAFT
Última actualización: 2026-06-21 (sesión noche)

## DATOS GENERALES
- Carpeta local: `/home/fernan/cubocraft/`
- GitHub: `github.com/fermounts/cubocraft`
- Web: `https://cubocraft.onrender.com`
- Spreadsheet ID: `1X819OQZwYdu7ldCBYWVxnxBSd7nJAlcGpvjNQw1iSBA`
- Link directo Sheet: `https://docs.google.com/spreadsheets/d/1X819OQZwYdu7ldCBYWVxnxBSd7nJAlcGpvjNQw1iSBA`
- Institución TFI: IFTS N°33 — Tecnicatura Superior en Ciencia de Datos e IA
- Tutora TFI: Marisa Cánovas

## STACK TECNOLÓGICO
- Backend: Flask (Python)
- Base de datos: Google Sheets (via gspread + Service Account)
- Bot WhatsApp: Twilio (recomendación futura: migrar a API oficial Meta)
- IA: Gemini 2.5 Flash (google-generativeai)
- Hosting: Render (web) + UptimeRobot (mantiene Render despierto)

## ARCHIVOS CLAVE EN /home/fernan/cubocraft/
- `webhook_server.py` — servidor Flask principal, recibe mensajes de Twilio
- `bot_handler.py` — lógica del bot, selector CUBO/CRAFT, menú por perfil
- `whatsapp_client.py` — cliente Twilio para enviar mensajes
- `sheets_client.py` — conexión y operaciones con Google Sheets
- `config.py` — variables de configuración
- `session_store.py` — manejo de sesiones de usuario
- `setup_sheets.py` — script para crear/configurar el Sheet desde cero
- `poblar_fichas_tecnicas.py` — script anterior para fichas (chocó con rate limit)
- `completar_sheet.py` — script nuevo (creado 2026-06-06) que reemplaza al anterior
- `credentials.json` — Service Account de Google (copiado de cubocraft-494603-1448c3760a76.json)
- `cubocraft-service-account.json` — archivo original de credenciales (mismo contenido)
- `requirements.txt` — dependencias del proyecto
- `Procfile` — configuración para Render

## ESTADO DEL GOOGLE SHEET

### Nombres reales de hojas (todos en MAYÚSCULAS)
VENDEDORES, PRODUCTOS, PEDIDOS, PAGOS, CAMPAÑAS, RANKING, CANDIDATOS,
CONOCIMIENTO_TECNICO, FICHAS_TECNICAS_BORRADOR, BASE_CONOCIMIENTO, PENDIENTES_VALIDACION

### Hojas con datos reales
- **VENDEDORES** — 3 registros. Columnas: ID, Nombre, Teléfono, Zona, Perfil, Activa, **Empresa** (AMBAS para los 3), **PIN** (V001=1111, V002=2222, V003=3333 por defecto)
- **PRODUCTOS** — 80 productos (40 EPP + 40 Materiales de Construcción)
- **PEDIDOS** — 12 pedidos: 3 de Fernando (reales), 4 de Fernanda y 4 de Tomás (prueba), 1 de Fernanda CANCELADO (P20260619031234 — ver abajo)
- **CONOCIMIENTO_TECNICO** — 11 normativas completas
- **BASE_CONOCIMIENTO** — 72 fichas generadas; 14 Aprobadas (4 calzado + 5 cascos + 5 guantes), resto Borrador; 7 pendientes + 1 error
- **RANKING** — calculado con datos reales de junio 2026 (actualizado 2026-06-16)

### Hojas completadas 2026-06-06
- **PAGOS** — 5 registros de prueba; columna Anulado eliminada (ver abajo)
- **CAMPAÑAS** — 2 campañas activas cargadas
- **CANDIDATOS** — 3 prospectos de muestra

### RANKING — datos reales junio 2026 (actualizado 2026-06-16)
| Pos | Vendedor | Total mes | Categoría |
|-----|----------|-----------|-----------|
| #1  | Fernando (V001) | $112.837,50 | Oro    |
| #2  | Fernanda (V002) | $68.752,50  | Plata  |
| #3  | Tomás    (V003) | $40.280,00  | Bronce |

El bot muestra el ranking correcto: opción 5 calcula en tiempo real desde PEDIDOS filtrando
por prefijo de producto (EPP→CUBO, MC→CRAFT). Marca "← vos" al vendedor actual.

### BASE_CONOCIMIENTO — EN PROCESO (72/80 al 2026-06-21)
- 72/80 fichas generadas; se corta por límite diario de Gemini (20 req/día free tier)
- **14 Aprobadas**: 4 calzado (EPP-010/011/012/013) + 5 cascos (EPP-001/002/CAB-03/04/05) + 5 guantes (EPP-006/007/008/009/MAN-05)
- **7 pendientes:** MC-AIS-04, EPP-AUD-05, EPP-CAL-05, EPP-ALT-05, EPP-RES-04, EPP-RES-05, EPP-CUE-04
- **1 error persistente:** EPP-CUE-05 (Impermeable PVC Ombu Naranja)
- Para retomar: `python3 completar_sheet.py --solo-fichas`
- Checkpoint en: `completar_sheet_progress.json`
- Delay entre requests: 65 segundos; 90 extra si hay rate limit 429

## ESTRUCTURA DE COLUMNAS (definitiva)

### PEDIDOS (12 columnas)
ID_Pedido | Fecha | ID_Vendedor | Nombre_Vendedor | ID_Producto | Nombre_Producto |
Cantidad | Precio_Unit | Descuento_Pct | Total | ID_Campaña | Estado

Estados válidos: PENDIENTE · CANCELADO

⚠️ Los pedidos P20260602135317 y P20260602140406 (los primeros de prueba) tienen columnas
desplazadas por el bug original — Fecha tiene "V001" y ID_Campaña tiene la fecha.
Corregir a mano en el Sheet si se necesitan. (Todos los demás pedidos están correctos.)

### PAGOS (8 columnas — columna Anulado eliminada el 2026-06-06)
ID_Pago | Fecha | ID_Vendedor | Nombre_Vendedor | Monto | Metodo | Comprobante | Estado

Estados válidos: PENDIENTE · CONFIRMADO · ANULADO
El saldo se calcula excluyendo pagos con Estado = ANULADO.

## CAMBIOS EN CÓDIGO (2026-06-06)

### sheets_client.py
- **Bug corregido**: `registrar_pedido()` y `registrar_pago()` tenían Fecha al final
  en lugar de la posición 2 — todos los campos estaban desplazados una columna.
- **`get_saldo()`**: ahora filtra `Estado != "ANULADO"` para no contar pagos anulados.
- **Nuevas funciones**:
  - `get_pedidos_pendientes(vendedor)` — pedidos PENDIENTE del vendedor
  - `cancelar_pedido(id_pedido, id_vendedor)` — cambia Estado a CANCELADO
  - `get_pagos_confirmados_todos()` — todos los pagos CONFIRMADO (para supervisor)
  - `anular_pago(id_pago)` — cambia Estado a ANULADO

### bot_handler.py
- **Nuevos estados**: CANCELAR_PEDIDO, CANCELAR_PEDIDO_CONFIRM, ANULAR_PAGO, ANULAR_PAGO_CONFIRM
- **Comando global vendedor**: "cancelar pedido" → flujo para cancelar pedido PENDIENTE
- **Comando global supervisor**: "anular pago" → flujo para anular pago CONFIRMADO
- En ambos casos se notifica al supervisor por WhatsApp al confirmar.

### Flujo cancelar pedido (vendedor)
```
cancelar pedido → lista de PENDIENTE → número → confirmación SI/NO → CANCELADO
```

### Flujo anular pago (solo supervisor)
```
anular pago → lista de CONFIRMADO → número → confirmación SI/NO → ANULADO
```

## CAMBIOS EN CÓDIGO (2026-06-15)

### Análisis crítico realizado
Se detectaron 18 problemas priorizados. Ver análisis completo en conversación.
Los 3 más críticos fueron corregidos en esta sesión.

### sheets_client.py
- **Fix saldo real**: `registrar_pago()` ahora graba `Estado = "PENDIENTE"` en lugar de
  `"CONFIRMADO"`. El saldo ya no incluye pagos no confirmados.
- **Nuevas funciones**:
  - `get_vendedor_by_id(vid)` — busca vendedor por ID (para notificar al confirmar pago)
  - `get_pagos_pendientes_todos()` — lista de pagos PENDIENTE de todos los vendedores
  - `confirmar_pago(id_pago)` — cambia PENDIENTE → CONFIRMADO
- **Fix BASE_CONOCIMIENTO**: `get_base_conocimiento()` usa `expected_headers` para
  evitar el error por columnas vacías duplicadas (fichas técnicas tienen 12 cols,
  hoja tiene 7 headers definidos).

### bot_handler.py
- **Fix #1 — Saldo real**: opción 3 "Ver mi saldo" ahora usa `get_balance_vendedor()`
  en lugar de `get_saldo()`. Muestra deuda real (pedidos − pagos confirmados) y
  crédito disponible. Informa pagos en revisión si los hay.
- **Fix #2 — Contexto IA**: nueva función `_ficha_a_contexto(r)` detecta si un registro
  de BASE_CONOCIMIENTO es una ficha técnica o una Q&A del pipeline de validación,
  y extrae el contenido útil en ambos casos. Antes el contexto enviado a Gemini
  era vacío para todas las fichas.
- **Fix #3 — Flujo de pagos con confirmación**:
  - Opción 9 (supervisor) ahora abre sub-menú: A=candidatas / B=confirmar-rechazar pagos
  - Nuevos estados: SUPER_MENU, SUPER_CONFIRMAR_PAGO, SUPER_CONFIRMAR_PAGO_CONFIRM
  - Al registrar pago el vendedor ve "enviado para revisión"
  - El supervisor recibe notificación con instrucción para abrir el panel (9 → B)
  - Al confirmar o rechazar se notifica al vendedor por WhatsApp

### Flujo pago (actualizado)
```
vendedor: monto → método → comprobante → SI → graba PENDIENTE → supervisor notificado
supervisor: panel 9 → B → C1/R1 → SI → CONFIRMADO/ANULADO → vendedor notificado
```

### completar_sheet.py (bug corregido 2026-06-15)
- `get_all_records()` fallaba con headers vacíos duplicados en BASE_CONOCIMIENTO.
  Reemplazado por `get_all_values()` con mapeo manual de columnas.
- La lectura del ESTADO también usa los datos en memoria (evita llamadas extra a Sheets API).

### BASE_CONOCIMIENTO — estructura real vs esperada
- Headers reales de la hoja (creados por pipeline Q&A): ID, CATEGORIA, PREGUNTA,
  RESPUESTA_VALIDADA, FUENTE_ORIGINAL, VALIDADO_POR, FECHA_VALIDACION
- Las fichas técnicas generadas por completar_sheet.py se almacenan en esas columnas
  con mapping: nombre→CATEGORIA, apertura→PREGUNTA, DESCRIPCION→RESPUESTA_VALIDADA,
  MODO_USO→FUENTE_ORIGINAL
- `_ficha_a_contexto()` maneja ambos tipos transparentemente

## ESTADO BOT WHATSAPP — OPERATIVO
- Selector CUBO/CRAFT al inicio
- Menú por perfil de usuario
- Pedidos: toma pedido → registra en hoja PEDIDOS del Sheet
- IA con context stuffing: inyecta BASE_CONOCIMIENTO + CONOCIMIENTO_TECNICO completo
- Pipeline validación: PENDIENTES_VALIDACION → BASE_CONOCIMIENTO (job horario)
- Resumen diario al supervisor a las 20hs Argentina
- Job semanal de ranking: lunes 9:00hs ARG, mensajes automáticos por posición (2026-06-19)
- Control de crédito $100.000: rechaza pedidos que superen el disponible antes de grabar en Sheet (2026-06-19)
- Notificación al supervisor incluye monto por ítem y total general del pedido (2026-06-19)
- Cancelación de pedidos y anulación de pagos operativos (2026-06-06)
- Pagos con confirmación del supervisor (2026-06-15): graba PENDIENTE, supervisor confirma desde panel 9→B
- Mensajes "join [keyword]" del sandbox de Twilio ignorados silenciosamente (2026-06-16)
- Logging detallado en webhook: From, Body, estado de sesión, errores con stack trace
- Ranking (opción 5) operativo (2026-06-18): muestra ranking real del mes filtrado por empresa de la sesión

## ESTADO WEB — OPERATIVA
- 3 secciones: Hub central / CUBO / CRAFT
- Carrusel EPP en CUBO (imágenes WebP, 97% menos peso)
- Carrusel CRAFT (mampostería, estructura, durlock)
- Badge UOCRA con efecto animado
- UptimeRobot manteniendo Render despierto
- **Dashboard en /dashboard** (2026-06-18): login por WhatsApp + PIN, vistas supervisor y vendedor

## ESTADO TFI
- Documento actual: CUBOCRAFT_TFI_v5.docx (en carpeta Proyecto Integrador de Drive)
- Correcciones de tutora aplicadas en v5: context stuffing en lugar de RAG
- Pendiente: agregar datos reales de pruebas en secciones 4.2 y 4.5

## CAMBIOS EN CÓDIGO (2026-06-19) — Control de crédito y notificación con totales

### bot_handler.py — Fix 1: tope de crédito antes de grabar

En `_handle_pedido_cantidad()`, inmediatamente después de calcular `total_item` y
antes de hacer `session_store.set(..., PEDIDO_CONFIRMAR)`:

- Llama a `sheets_client.get_balance_vendedor(vendedor)` para obtener `disponible`.
- Suma el carrito actual (`total_carrito`) + el ítem nuevo (`total_item`).
- Si supera `disponible`: rechaza con mensaje que indica cuántas unidades máximas puede
  pedir y sugiere hacer un depósito (opción 2). **No graba nada en el Sheet.**
- El estado permanece en `PEDIDO_CANTIDAD` para que el vendedor reintente con menos.

`LIMITE_CREDITO = 100_000` hardcodeado en `config.py`. La fórmula de disponible:
```
disponible = LIMITE_CREDITO - (deuda_real - pagos_pendientes)
```
donde `deuda_real` = suma de PEDIDOS PENDIENTE del vendedor, `pagos_pendientes` =
suma de PAGOS PENDIENTE (crédito provisional mientras el supervisor confirma).

### bot_handler.py — Fix 2: monto total en notificación y confirmación

En `_cerrar_pedido()`:
- Antes de registrar en el Sheet, calcula `precio_u × qty × (1 − disc/100)` por ítem.
- Acumula `total_general`.
- La notificación al supervisor ahora incluye precio por línea + `*TOTAL: $xxx*`.
- La confirmación al vendedor también muestra el total del pedido.

### Corrección de datos — Pedido fantasma de Fernanda

Pedido `P20260619031234` (Fernanda, 100 × Pantalla Facial Steelpro FP200, $612,000,
Estado PENDIENTE) fue registrado antes de implementar el control de crédito.
Cancelado manualmente con `sheets_client.cancelar_pedido("P20260619031234", "V002")`.

Balance de Fernanda antes/después:
- **Antes**: deuda $757,252.50 / disponible −$657,252.50
- **Después**: deuda $145,252.50 / disponible −$45,252.50

---

## CAMBIOS EN CÓDIGO (2026-06-19) — Job semanal de ranking

### sheets_client.py
- `get_vendedores_activos()`: retorna lista de vendedores con Activa=SI.
- `calcular_ranking_semanal(inicio, fin)`: ranking combinado de todos los productos
  en el rango de fechas dado; incluye campo `Aperturas` con categorías vendidas.

### bot_handler.py
- `generar_mensaje_coaching(nombre, total_semana, aperturas_vendedor, aperturas_lider)`:
  genera mensaje de coaching con Gemini 2.5 Flash para el último puesto del ranking.
  Sugiere categorías que no trabajó el vendedor (las del líder) sin mencionar al líder.
  Usa `max_output_tokens=8192` — gemini-2.5-flash es un modelo de "thinking" que consume
  tokens internamente; con budget bajo el output real quedaba truncado.
  Tiene fallback con mensaje hardcoded si Gemini falla.

### webhook_server.py
- `_enviar_ranking_semanal()`: calcula semana anterior (lunes→domingo), genera y
  envía un mensaje personalizado a cada vendedor en el ranking:
  - #1: felicitación ("mejor vendedor/a")
  - #2..penúltimo: motivación (muestra diferencia al líder en $)
  - Último: coaching generado por Gemini (sugiere categorías sin nombrar al líder)
- Scheduler: job `ranking_semanal` → `CronTrigger(day_of_week="mon", hour=9, minute=0)`
- Si no hay ventas en la semana, no envía mensajes y loguea el motivo.

### Scheduler completo
| Job                  | Trigger                        |
|----------------------|-------------------------------|
| resumen_diario       | Lunes-Domingo 20:00 ARG        |
| procesar_pendientes  | Cada 1 hora                    |
| ranking_semanal      | Lunes 09:00 ARG                |

## CAMBIOS EN CÓDIGO (2026-06-18) — Dashboard

### VENDEDORES — columna PIN agregada
- Nueva columna H: `PIN` con valores por defecto 1111/2222/3333.
- Usada para autenticación en el dashboard web.

### sheets_client.py — funciones de dashboard
- `validar_login(phone, pin)`: valida número de WhatsApp + PIN, devuelve dict del vendedor.
- `_safe_float(v)`: helper para parsear totales con coma/punto.
- `_calcular_ranking_total(mes, pedidos)`: ranking combinado (todos los productos) del mes.
- `get_dashboard_supervisor()`: total mes, pedidos, pagos pendientes, acumulado año, ranking, campañas.
- `get_dashboard_vendedor(vid)`: ventas mes, pedidos, deuda real, disponible, acumulado año, posición.

### webhook_server.py — rutas del dashboard
- `app.secret_key = config.SECRET_KEY` para sesiones Flask firmadas.
- `GET  /dashboard` → sirve dashboard.html
- `POST /api/login` → valida phone+PIN, crea sesión; rol supervisor si phone == SUPERVISORA_PHONE
- `GET  /api/dashboard-data` → datos según rol (requiere sesión)
- `POST /api/logout` → limpia sesión

### dashboard.html — nueva página
- SPA sin dependencias externas (solo Google Fonts ya usadas).
- Login → pantalla centrada con form WhatsApp + PIN.
- Sesión persistente: si hay sesión activa al entrar, va directo al dashboard.
- Vista Supervisor: 4 KPIs (total mes, pedidos, pagos pendientes, acumulado año) + ranking + campañas.
- Vista Vendedor: 4 KPIs (ventas, pedidos, deuda, acumulado año) + posición en ranking.
- Mes en curso automático, no hardcodeado.
- Estética idéntica a index.html (Barlow Condensed + Inter, paleta navy/blue/orange).

⚠️ **Agregar `SECRET_KEY` como variable de entorno en Render** para seguridad en producción
   (por defecto usa "changeme" definido en config.py).

## CAMBIOS EN CÓDIGO (2026-06-18) — Ranking y Empresa

### VENDEDORES — columna Empresa agregada
- Nueva columna G: `Empresa` con valor `AMBAS` para los 3 vendedores existentes.
- `pasar_candidata_a_vendedoras()` ahora incluye `"AMBAS"` al crear vendedores nuevos.
- `get_vendedora_by_phone()` y `get_vendedor_by_id()` devuelven el campo `Empresa` automáticamente.

### sheets_client.py — Ranking reescrito
- Eliminada `get_ranking_vendedora()` (buscaba columna `Período` que no existe).
- Nueva función `calcular_ranking_empresa(empresa)`: calcula ranking en tiempo real desde
  la hoja PEDIDOS, filtrando por prefijo de ID_Producto (EPP→CUBO, MC→CRAFT),
  excluyendo CANCELADOS, filtrando por mes actual.
- Retorna lista ordenada de dicts con Posición, Nombre, Total_Mes, Categoría.

### bot_handler.py — Opción 5 operativa
- Usa `calcular_ranking_empresa(empresa)` con la empresa de la sesión actual.
- Muestra ranking completo del mes con 🥇🥈🥉 y marca "← vos" al vendedor actual.
- Si empresa es CUBO y el vendedor eligió CUBO en esa sesión → ve ranking de EPP.
- Si elige CRAFT → ve ranking de materiales de construcción.

## CAMBIOS EN CÓDIGO (2026-06-16)

### webhook_server.py
- **try/except alrededor de `bot_handler.procesar()` y `enviar()`**: antes una excepción
  devolvía 500 a Twilio que lo interpretaba como fallo silencioso. Ahora siempre devuelve 200.
- **Logging detallado al inicio del webhook**: loguea `From`, `Body`, `NumMedia`, estado de
  sesión, nombre del vendedor y longitud de la respuesta generada.
- **`/debug-config` endpoint**: muestra qué variables de entorno están seteadas en producción
  (sin exponer valores). Útil para diagnosticar Render: `curl https://cubocraft.onrender.com/debug-config`

### bot_handler.py
- **Guard para mensajes "join [keyword]"**: cuando un número nuevo entra al sandbox de Twilio
  manda "join keyword". Antes el bot lo trataba como pregunta libre y llamaba a Gemini.
  Ahora retorna `""` y el webhook no intenta enviar respuesta.
- **Logs adicionales en `procesar()`**: estado, empresa y nombre del vendedor en cada llamada.

### whatsapp_client.py
- **Validación explícita de credenciales**: `_enviar_twilio()` verifica que
  `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` y `TWILIO_PHONE_NUMBER` estén seteados
  antes de intentar enviar. Antes fallaba silenciosamente con excepción atrapada.

### requirements.txt
- `gspread>=6.2.1` — versión mínima fijada para garantizar soporte de `expected_headers`
  en `get_all_records()`. Sin esto Render podía instalar una versión anterior y fallar.

### PEDIDOS — correcciones de datos (2026-06-16, vía script directo al Sheet)
- 8 fechas de V002 (Fernanda) y V003 (Tomás) normalizadas: `2026-06-XX` → `2026-06-XX 00:00:00`
- `P20260612001` Total: `9562,5` → `9562.5` (coma → punto)

### RANKING — calculado con datos reales junio 2026 (2026-06-16)
- Reemplazó los datos estáticos de prueba por el ranking calculado de los 11 pedidos de junio.
- Calculado con script directo al Sheet (no hay job automático aún).

## CAMBIOS EN CÓDIGO (2026-06-21) — Calidad BASE_CONOCIMIENTO y bugs del bot

### Problema raíz: alucinaciones de normas en las fichas técnicas
Gemini inventó normas que no existen: `IRAM-3627` para calzado (la real es `IRAM 3610`) y normas
inventadas para cascos. Se detectó al revisar una respuesta del bot sobre calzado para obra húmeda.

### Corrección de normas en el Sheet (BASE_CONOCIMIENTO)
- **EPP-010/011/012/013** (calzado): campo NORMATIVA col 9 corregido de `IRAM-3627` → `IRAM 3610
  (Calzado de seguridad, calzado de protección y calzado de trabajo)`. ESTADO → Aprobado.
- **EPP-001/002/CAB-03/CAB-04/CAB-05** (cascos): regeneradas con prompt corregido y NORMATIVA
  verificada contra fuentes reales (Cámara Argentina de Seguridad, IRAM, Dilva):
  - IRAM 3620 — Tipo 1, Clase B (EPP-002 dieléctrico, 20.000 V) / Clase C (resto)
  - Vida útil 2–5 años, equivalencias EN 397 / ANSI Z89.1. ESTADO → Aprobado.

### Corrección en código (norma hardcodeada)
- `bot_handler.py` system prompt: `IRAM 3627 calzado` → `IRAM 3610 calzado`
- `setup_sheets.py`: `IRAM-3627` → `IRAM-3610` en PRODUCTOS y CONOCIMIENTO_TECNICO
  (para que una futura re-siembra no reintroduzca el error)

### PROMPT_FICHA reescrito (completar_sheet.py)
- Regla absoluta: "NUNCA inventar números de normas, valores numéricos, voltajes,
  temperaturas, certificaciones que no estén textualmente en la Especificación_Técnica"
- Si un dato no figura en la spec → `"No especificado en la ficha técnica del proveedor"`
- Campo NORMATIVA: copiar textualmente de `{especificacion}`, no de `{norma}` si no
  aparece también en la especificación

### Filtro ESTADO=Borrador en get_base_conocimiento()
- Antes: `get_all_records(expected_headers=...)` devolvía todos los registros sin filtrar
- Ahora: usa `get_all_values()`, lee col 12 (ESTADO), excluye ESTADO=Borrador
- Registros Q&A del pipeline (sin col 12) se incluyen siempre
- Efecto: el bot ya no puede responder con datos no validados de fichas en Borrador

### Fix encadenado: NORMATIVA nunca llegaba a Gemini
- `get_base_conocimiento()` no leía col 9 (NORMATIVA) — ahora agrega clave `NORMATIVA` al dict
- `_ficha_a_contexto()` no incluía NORMATIVA en la cadena de contexto — ahora la incluye,
  omitiendo los valores "No especificado…" para no contaminar el contexto

### max_output_tokens 400 → 800 (bot_handler.py)
- Con 400 tokens Gemini truncaba respuestas con datos cuantitativos (normativas, valores técnicos)
- Aumentado a 800 para permitir respuestas completas con datos verificables

### Fix bug: opción "6" no reconocida en estado POST_ACCION
- **Síntoma**: vendedor en POST_ACCION escribe "6" para ir a Consulta IA → bot no lo reconoce
- **Causa**: `_handle_post_accion()` solo aceptaba "1" (volver al menú) y "2" (hasta pronto);
  cualquier otro input recibía el prompt `"1️⃣ Volver al menú | 2️⃣ Hasta pronto"` y se descartaba
- **Fix**: si el input está en `_MENU_MAP` (opciones 1–8), se ejecuta directamente via
  `_ejecutar_accion()`. Si es "9" y es supervisor, abre el panel. Mejora UX general:
  desde POST_ACCION se puede saltar a cualquier opción sin pasar por el menú.

### API key de Gemini comprometida y reemplazada
- La key anterior (`AIza...`) fue detectada como "leaked" por Google (403) tras un push.
  **Causa probable**: la key estaba en algún archivo pusheado al repo en algún momento anterior.
- Se generó nueva key desde Google AI Studio y se configuró en Render (Environment) y
  localmente via `~/.bashrc`. Variable: `GEMINI_API_KEY`.
- ⚠️ Verificar que `.gitignore` cubra todos los archivos con credenciales antes de cada push.

### Limitación de pruebas: Twilio Sandbox
- El sandbox de Twilio tiene límite diario de mensajes salientes. Esto bloqueó pruebas en vivo
  durante la sesión. Afecta notificaciones al supervisor y mensajes de coaching del ranking semanal.
- Solución definitiva: migrar a API oficial WhatsApp Business (Meta) — pendiente en lista.

### Script regenerar_cascos.py (nuevo archivo)
- Script one-shot para regenerar fichas de cascos con el prompt corregido y mostrar resultados
  para revisión manual antes de aprobar. Ubicado en `/home/fernan/cubocraft/regenerar_cascos.py`.
- No se commitea al repo (es una herramienta de mantenimiento temporal).

## CAMBIOS EN CÓDIGO (2026-06-21 noche) — Guantes: normas corregidas y fichas aprobadas

### Hallazgo: IRAM-3649 mal asignada a todos los guantes en PRODUCTOS
- `IRAM-3649` es la norma para **equipos de protección respiratoria** (filtros), NO para guantes.
  Estaba asignada erróneamente a los 5 productos de guantes en la columna `ID_Norma_Ref` de PRODUCTOS.
- Detectado al revisar las fichas de guantes antes de regenerarlas.

### Corrección en PRODUCTOS (ID_Norma_Ref — 5 filas)
| ID | Producto | Norma incorrecta | Norma correcta |
|---|---|---|---|
| EPP-006 | Guantes de Cuero Vaqueta T8 | IRAM-3649 | IRAM-3600-1 |
| EPP-007 | Guantes de Cuero Vaqueta T9 | IRAM-3649 | IRAM-3600-1 |
| EPP-008 | Guantes de Nitrilo Negro T8 (caja x100) | IRAM-3649 | IRAM-3609-1 |
| EPP-009 | Guantes de Nitrilo Naranja Grip T9 | IRAM-3649 | IRAM-3607 |
| EPP-MAN-05 | Guante Anticorte Steelpro CUT-5 Nivel F T9 | IRAM-3649 | IRAM-3607 |

Criterio de asignación de normas (verificado):
- **IRAM 3600-1** — Guantes de cuero y cuero combinado (riesgos mecánicos generales)
- **IRAM 3607** — Guantes contra riesgos mecánicos (niveles de desempeño abrasión/corte/desgarro/perforación)
- **IRAM 3609-1** — Guantes contra productos químicos y microorganismos

### Fichas regeneradas en BASE_CONOCIMIENTO con ESTADO=Aprobado
- **EPP-006/007** (cuero): NORMATIVA = `IRAM 3600-1 — Guantes de protección. Parte 1: cuero vacuno/descarne. Riesgos mecánicos generales. Vida útil: reemplazar ante perforaciones, costuras sueltas o cuero endurecido.`
- **EPP-008** (nitrilo negro descartable): NORMATIVA = `IRAM 3609-1 — Guantes contra productos químicos y microorganismos. Uso único — no reutilizar. Verificar compatibilidad química antes del uso.`
- **EPP-009** (nitrilo naranja grip): NORMATIVA = `IRAM 3607 — Guantes contra riesgos mecánicos. Resistencia a corte Nivel B (escala A–F). Recubrimiento nitrilo mejora agarre en húmedo/aceitoso.`
- **EPP-MAN-05** (anticorte Steelpro CUT-5): NORMATIVA = `IRAM 3607 — Corte Nivel F (máximo). HPPE + fibra de acero inox. Equiv.: EN 388:2016+A1:2018 / ANSI/ISEA 105.`
- Todas grabadas directamente con ESTADO=Aprobado (normativa verificada por humano, no por Gemini).

### Script regenerar_guantes.py (nuevo archivo)
- Modela el mismo patrón que `regenerar_cascos.py`: Gemini genera descripción/modo_uso/precauciones,
  la NORMATIVA se hardcodea con datos verificados (nunca se usa la de Gemini).
- Ubicado en `/home/fernan/cubocraft/regenerar_guantes.py`.
- No se commitea al repo (herramienta de mantenimiento temporal).

### Estado validado de 3 categorías EPP (al 2026-06-21)
| Categoría | IDs | Norma | Estado |
|---|---|---|---|
| Calzado | EPP-010/011/012/013 | IRAM 3610 | ✅ Aprobado |
| Cascos | EPP-001/002/CAB-03/04/05 | IRAM 3620 (Clase B para dieléctrico, Clase C para el resto) | ✅ Aprobado |
| Guantes | EPP-006/007/008/009/MAN-05 | IRAM 3600-1 / 3607 / 3609-1 según material | ✅ Aprobado |

### Limitación de pruebas: Twilio Sandbox (sigue activa)
- El sandbox de Twilio tiene límite diario de mensajes salientes que se resetea esta noche.
- Bloqueó todas las pruebas en vivo de la sesión (notificaciones al supervisor, coaching de ranking).
- Workaround: esperar reset nocturno o usar número Twilio con plan pago.
- Solución definitiva pendiente: migrar a API oficial WhatsApp Business (Meta).

## CAMBIOS EN CÓDIGO (2026-06-21) — Fix zona horaria

### sheets_client.py y bot_handler.py
- **Bug:** `datetime.now()` sin TZ devolvía UTC en Render. Un pedido a las 23:32 ARG
  se grababa como 02:32 del día siguiente en PEDIDOS/PAGOS/BASE_CONOCIMIENTO.
- **Fix:** agregado `import pytz` y `_TZ_ARG = pytz.timezone("America/Argentina/Buenos_Aires")`
  en ambos archivos. Todos los `datetime.now()` reemplazados por `datetime.now(_TZ_ARG)`.
- Afecta: timestamps de PEDIDOS, PAGOS, BASE_CONOCIMIENTO, CANDIDATOS, IDs generados con fecha,
  y el display del mes en el ranking (opción 5 del bot).
- `webhook_server.py` usa `date.today()` en el job de las 9:00 ARG (12:00 UTC) — sin riesgo
  de desfase, no se tocó.

## PENDIENTES DEL PROYECTO
1. ⚠️ **Agregar `SECRET_KEY` en Render** (variables de entorno) para seguridad del dashboard
2. Completar BASE_CONOCIMIENTO — faltan 7 fichas + 1 error persistente (EPP-CUE-05)
   - Pendientes: MC-AIS-04, EPP-AUD-05, EPP-CAL-05, EPP-ALT-05, EPP-RES-04, EPP-RES-05, EPP-CUE-04
   - Comando: `GEMINI_API_KEY="..." python3 completar_sheet.py --solo-fichas`
3. ~~Regenerar fichas de guantes~~ — **RESUELTO 2026-06-21** (EPP-006/007/008/009/MAN-05 Aprobadas, normas verificadas)
4b. Aprobar/regenerar las ~58 fichas restantes en ESTADO=Borrador (revisar normas inventadas)
4. Corregir 2 pedidos con columnas desplazadas (P20260602135317, P20260602140406) — a mano en Sheet
5. Probar flujo completo pedido punta a punta (incluye que el tope de crédito rechace correctamente)
6. Probar flujo pago → supervisor confirma → vendedor notificado
7. ~~Fix ranking en el bot~~ — **RESUELTO 2026-06-18**
8. ~~Control de crédito~~ — **RESUELTO 2026-06-19** (rechaza antes de grabar, sugiere depósito)
9. ~~Fix zona horaria UTC~~ — **RESUELTO 2026-06-21** (todas las fechas usan ARG)
10. ~~Fix "6" no reconocido en POST_ACCION~~ — **RESUELTO 2026-06-21**
11. Sin tabla CLIENTES — no hay registro de a quién vende el vendedor
12. Descuento de campaña se evalúa por item, no por total del carrito (bug de lógica)
13. Fotos reales carrusel CRAFT
14. Imagen corporativa hub central
15. Migrar WhatsApp de Twilio a API oficial Meta (soluciona límite diario sandbox)
16. Agregar datos reales en TFI secciones 4.2 y 4.5
17. Hacer configurable el límite de crédito por vendedor (hoy es $100.000 global en config.py)

## PROBLEMAS CONOCIDOS — sin corregir aún
- ~~**Ranking en el bot**~~: resuelto 2026-06-18.
- ~~**Opción "6" en POST_ACCION**~~: resuelto 2026-06-21.
- **Descuento**: `aplicar_mejor_descuento()` recibe subtotal de un item, no total del carrito.
- **Baja**: solicitud no toca VENDEDORES, no desactiva al vendedor.
- **Panel supervisor**: sin flujo para validar consultas IA desde el bot.
- **Sin CLIENTES**: pedidos no registran el cliente final.
- **Límite de crédito**: $100.000 hardcodeado en `config.py` (no por vendedor). El control ya se aplica.
- **Twilio Sandbox**: límite diario de mensajes salientes bloquea pruebas en vivo.
  Workaround temporal: esperar reset o usar número Twilio con plan pago. Solución definitiva: Meta API.
- **Fichas en Borrador**: ~58 fichas generadas con prompt viejo pueden tener normas inventadas.
  14 ya Aprobadas (4 calzado + 5 cascos + 5 guantes). Revisar y aprobar el resto manualmente,
  o regenerar por lotes usando `regenerar_cascos.py` / `regenerar_guantes.py` como modelo.
- **IRAM-3649**: era la norma incorrecta asignada a los 5 guantes — ya corregida en PRODUCTOS y BASE_CONOCIMIENTO.

## CÓMO USAR ESTE ARCHIVO
Al inicio de cada sesión decile a Claude Code:
leé el CONTEXTO.md y arrancamos desde ahí

Al final de cada sesión decile:
actualizá el CONTEXTO.md con todo lo que hicimos hoy
