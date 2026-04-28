"""
set_render_env.py
Sube TODAS las variables del .env al servicio de Render via API REST.
- GOOGLE_CREDS_JSON: si apunta a un .json, lee el archivo y sube el JSON inline
- Vars vacías en .env: las omite (no sobreescribe las que ya existen en Render)

Uso: RENDER_API_KEY=rnd_xxx python3 set_render_env.py
"""

import json
import os
import sys
import urllib.request
import urllib.error

SERVICE_ID = "srv-d7kefs647okc73buqoq0"
API_BASE = "https://api.render.com/v1"

api_key = os.getenv("RENDER_API_KEY")
if not api_key:
    print("ERROR: exportá tu API key primero:")
    print("  export RENDER_API_KEY=rnd_xxxxxxxxxxxx")
    print("  python3 set_render_env.py")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def api_get(path):
    req = urllib.request.Request(f"{API_BASE}{path}", headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def api_put(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method="PUT")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def load_env_file(path=".env") -> dict:
    """Lee el .env y devuelve {clave: valor}, resolviendo GOOGLE_CREDS_JSON si es archivo."""
    result = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if not val:
                continue  # omitir vars vacías
            if key == "GOOGLE_CREDS_JSON" and val.endswith(".json") and os.path.isfile(val):
                with open(val) as jf:
                    val = json.dumps(json.load(jf), ensure_ascii=False)
            result[key] = val
    return result


# 1. Leer vars locales
print("Leyendo .env...")
local_vars = load_env_file()
print(f"  → {len(local_vars)} variables con valor:")
for k, v in local_vars.items():
    display = v[:40] + "..." if len(v) > 40 else v
    print(f"     {k} = {display}")

# 2. Obtener vars actuales de Render
print(f"\nObteniendo variables actuales de {SERVICE_ID}...")
try:
    existing = api_get(f"/services/{SERVICE_ID}/env-vars")
except urllib.error.HTTPError as e:
    print(f"ERROR {e.code}: {e.read().decode()}")
    sys.exit(1)

render_vars = {item["envVar"]["key"]: item["envVar"]["value"]
               for item in existing if "envVar" in item}
print(f"  → {len(render_vars)} variables en Render: {list(render_vars.keys())}")

# 3. Mergear: local sobreescribe Render
merged = {**render_vars, **local_vars}
payload = [{"key": k, "value": v} for k, v in merged.items()]

# 4. Subir
print(f"\nSubiendo {len(payload)} variables a Render...")
try:
    api_put(f"/services/{SERVICE_ID}/env-vars", payload)
except urllib.error.HTTPError as e:
    print(f"ERROR {e.code}: {e.read().decode()}")
    sys.exit(1)

print("✓ Variables actualizadas:")
for k in local_vars:
    status = "actualizada" if k in render_vars else "nueva"
    print(f"  {k} [{status}]")
print("\nRender va a redeploy automáticamente.")
