from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from api.app import app

client = TestClient(app)


def code(payload):
    r = client.post("/v1/codigo", json=payload)
    assert r.status_code == 200, r.text
    return r.text.strip()


assert code({"texto": "factura", "use_llm": False}) == "01"
assert code({"texto": "boleta", "use_llm": False}) == "03"
assert code({"texto": "RUC", "modo": "identidad", "use_llm": False}) == "6"
assert code({"texto": "DNI", "modo": "identidad", "use_llm": False}) == "1"

base = {"empresa": "RC CORPORACION", "registro": "COMPRA", "use_llm": False}
assert code({"texto": "SERVICIO DE INTERNET 993630309", **base}) == "6365095|4212"
assert code({"texto": "ENERGIA ELECTRICA JR.1RO DE NOVIEMBRE", **base}) == "6361095|4212"
assert code({"texto": "ENERGIA ELECTRICA JR.LOS INCAS", **base}) == "6361095|4212"
assert code({"texto": "ENERGIA ELECTRICA JR.FCO.IRAZOLA", **base}) == "6361095|4212"

print("API OK")
