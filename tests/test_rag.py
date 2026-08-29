from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rag_engine import ContasisRAG

rag = ContasisRAG("data")

# Catalogs: no LLM required
assert rag.responder("factura", use_llm=False) == "01"
assert rag.responder("boleta", use_llm=False) == "03"
assert rag.responder("RUC", modo="identidad", use_llm=False) == "6"
assert rag.responder("DNI", modo="identidad", use_llm=False) == "1"

# Exact historical glosas: deterministic, codes only
assert rag.responder("SERVICIO DE INTERNET 993630309", empresa="RC CORPORACION", use_llm=False) == "6365095|4212"
assert rag.responder("ENERGIA ELECTRICA JR.1RO DE NOVIEMBRE", empresa="RC CORPORACION", use_llm=False) == "6361095|4212"
assert rag.responder("ENERGIA ELECTRICA JR.LOS INCAS", empresa="RC CORPORACION", use_llm=False) == "6361095|4212"
assert rag.responder("ENERGIA ELECTRICA JR.FCO.IRAZOLA", empresa="RC CORPORACION", use_llm=False) == "6361095|4212"

print("OK")
