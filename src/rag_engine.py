from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Optional

import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper().strip()
    # phone/document-like long numbers usually do not define the accounting concept
    text = re.sub(r"\b\d{5,}\b", " ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _read_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class ContasisRAG:
    """Hybrid RAG for Contasis codes.

    Important design rule: SmolLM2 never receives permission to invent an account.
    It may only choose from candidates retrieved from historical records / plan.
    """

    def __init__(self, data_dir: str | Path = "data", ollama_host: Optional[str] = None,
                 model: Optional[str] = None):
        self.data_dir = Path(data_dir)
        self.catalogos = json.loads((self.data_dir / "catalogos.json").read_text(encoding="utf-8"))
        self.historicos = _read_jsonl(self.data_dir / "historicos.jsonl")
        self.plan = _read_jsonl(self.data_dir / "plan_cuentas.jsonl")
        self.defaults = json.loads((self.data_dir / "account_total_defaults.json").read_text(encoding="utf-8"))
        self.ollama_host = (ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "contasis-smollm2")
        self._build_catalog_aliases()
        self._build_indexes()

    def _build_catalog_aliases(self):
        self.comprobante_aliases = {}
        for code, desc in self.catalogos["comprobantes"].items():
            self.comprobante_aliases[normalize(desc)] = code
        # Frequent natural-language aliases, ordered by semantic specificity later.
        extras = {
            "FACTURA": "01", "FACTURA ELECTRONICA": "01",
            "RECIBO DE HONORARIOS": "02", "RECIBO POR HONORARIOS": "02", "HONORARIOS": "02",
            "BOLETA": "03", "BOLETA DE VENTA": "03", "BOLETA ELECTRONICA": "03",
            "LIQUIDACION DE COMPRA": "04",
            "NOTA DE CREDITO": "07", "NOTA CREDITO": "07",
            "NOTA DE DEBITO": "08", "NOTA DEBITO": "08",
            "GUIA DE REMISION": "09", "GUIA REMISION": "09",
            "RECIBO POR ARRENDAMIENTO": "10", "ARRENDAMIENTO": "10",
            "TICKET": "12", "TICKET MAQUINA REGISTRADORA": "12",
            "DOCUMENTO ENTIDAD FINANCIERA": "13",
            "RECIBO SERVICIOS PUBLICOS": "14", "RECIBO SERVICIO PUBLICO": "14",
            "COMPROBANTE DE RETENCION": "20",
            "COMPROBANTE NO DOMICILIADO": "91",
            "CHEQUE": "CH", "DEPOSITO": "DP", "LIBRO DE ACTAS": "LA",
            "LETRA DE CAMBIO": "LE", "LIQUIDACION": "LI",
        }
        self.comprobante_aliases.update({normalize(k): v for k, v in extras.items()})

        self.identidad_aliases = {}
        for code, desc in self.catalogos["identidad"].items():
            self.identidad_aliases[normalize(desc)] = code
        self.identidad_aliases.update({
            "DNI": "1", "DOCUMENTO NACIONAL DE IDENTIDAD": "1",
            "CARNET DE EXTRANJERIA": "4", "CE": "4",
            "RUC": "6", "REGISTRO UNICO DE CONTRIBUYENTES": "6",
            "PASAPORTE": "7", "CEDULA DIPLOMATICA": "A", "CEDULA DIPLOMATICA DE IDENTIDAD": "A",
            "OTROS": "0",
        })

    def _build_indexes(self):
        self.hist_texts = []
        self.hist_exact = defaultdict(list)
        for i, r in enumerate(self.historicos):
            g = normalize(r.get("glosa", ""))
            p = normalize(r.get("razon_social", ""))
            d = normalize(r.get("cuenta_base_desc", ""))
            self.hist_texts.append(" ".join(x for x in (g, p, d) if x))
            if g:
                self.hist_exact[g].append(i)
        self.hist_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)
        self.hist_matrix = self.hist_vectorizer.fit_transform(self.hist_texts) if self.hist_texts else None

        self.plan_texts = [normalize(r.get("descripcion", "")) for r in self.plan]
        self.plan_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)
        self.plan_matrix = self.plan_vectorizer.fit_transform(self.plan_texts) if self.plan_texts else None

    def _catalog_lookup(self, text: str, aliases: dict[str, str]):
        q = normalize(text)
        if q in aliases:
            return aliases[q]
        # For phrases such as "registro de una factura", match the longest alias first.
        matches = [(len(alias), code) for alias, code in aliases.items() if alias and re.search(rf"\b{re.escape(alias)}\b", q)]
        if matches:
            matches.sort(reverse=True)
            return matches[0][1]
        return None

    def codigo_comprobante(self, text: str) -> str:
        return self._catalog_lookup(text, self.comprobante_aliases) or "00"

    def codigo_identidad(self, text: str) -> str:
        return self._catalog_lookup(text, self.identidad_aliases) or "0"

    def _allowed_hist_indices(self, empresa=None, registro=None):
        empresa_n = normalize(empresa) if empresa else None
        registro_n = normalize(registro) if registro else None
        idxs = []
        for i, r in enumerate(self.historicos):
            if empresa_n and normalize(r.get("empresa")) != empresa_n:
                continue
            if registro_n and normalize(r.get("registro")) != registro_n:
                continue
            idxs.append(i)
        return idxs

    def _default_total(self, empresa=None, registro="COMPRA"):
        registro = normalize(registro)
        if empresa:
            for emp, mapping in self.defaults.items():
                if emp != "_GLOBAL" and normalize(emp) == normalize(empresa):
                    if registro in mapping:
                        return str(mapping[registro])
        return str(self.defaults.get("_GLOBAL", {}).get(registro, "4212" if registro == "COMPRA" else "1212"))

    def retrieve(self, text: str, empresa=None, registro="COMPRA", top_k=6):
        q = normalize(text)
        allowed = self._allowed_hist_indices(empresa, registro)
        # exact normalized glosa wins; this is historical evidence, not model generation.
        exact = [i for i in self.hist_exact.get(q, []) if i in set(allowed)]
        if exact:
            candidates = []
            for i in exact[:top_k]:
                r = self.historicos[i]
                candidates.append({"source":"historico", "score":1.0, "record":r,
                                   "pair":f"{r['cuenta_base']}|{r['cuenta_total']}"})
            return candidates

        candidates = []
        if self.hist_matrix is not None and allowed:
            qv = self.hist_vectorizer.transform([q])
            scores = cosine_similarity(qv, self.hist_matrix[allowed]).ravel()
            order = scores.argsort()[::-1][:top_k]
            for pos in order:
                i = allowed[int(pos)]
                r = self.historicos[i]
                candidates.append({"source":"historico", "score":float(scores[int(pos)]), "record":r,
                                   "pair":f"{r['cuenta_base']}|{r['cuenta_total']}"})

        # Plan candidates are useful when the historical wording is novel.
        if self.plan_matrix is not None:
            qv = self.plan_vectorizer.transform([q])
            ps = cosine_similarity(qv, self.plan_matrix).ravel()
            order = ps.argsort()[::-1][:max(3, top_k // 2)]
            total = self._default_total(empresa, registro)
            for i in order:
                r = self.plan[int(i)]
                candidates.append({"source":"plan", "score":float(ps[int(i)]), "record":r,
                                   "pair":f"{r['codigo']}|{total}"})
        return candidates

    def _fallback_pair(self, candidates):
        # Aggregate evidence by candidate pair so repeated historical patterns beat one-off noise.
        agg = defaultdict(float)
        for rank, c in enumerate(candidates):
            weight = max(c["score"], 0.0) * (1.0 if c["source"] == "historico" else 0.45)
            weight *= 1.0 / (1.0 + 0.10 * rank)
            agg[c["pair"]] += weight
        if not agg:
            return f"|{self._default_total(None, 'COMPRA')}"
        return max(agg.items(), key=lambda kv: kv[1])[0]

    def _ollama_choose(self, text, candidates):
        # Keep only unique candidate pairs, in ranking order.
        unique = []
        seen = set()
        for c in candidates:
            if c["pair"] in seen:
                continue
            seen.add(c["pair"])
            unique.append(c)
            if len(unique) >= 8:
                break
        if not unique:
            return None
        lines = []
        allowed = []
        for c in unique:
            allowed.append(c["pair"])
            r = c["record"]
            if c["source"] == "historico":
                context = f"{r.get('glosa','')} / {r.get('razon_social','')}"
            else:
                context = r.get("descripcion", "")
            lines.append(f"{c['pair']} :: {context}")
        prompt = (
            "Entrada: " + text + "\n"
            "Elige SOLO una opción de esta lista. No inventes códigos. "
            "Responde exactamente BASE|TOTAL y nada más.\n" + "\n".join(lines)
        )
        try:
            resp = requests.post(
                f"{self.ollama_host}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0, "num_predict": 16}},
                timeout=25,
            )
            resp.raise_for_status()
            text_out = str(resp.json().get("response", "")).strip()
            m = re.search(r"([A-Z0-9]+)\s*\|\s*([A-Z0-9]+)", text_out.upper())
            if m:
                pair = f"{m.group(1)}|{m.group(2)}"
                if pair in allowed:
                    return pair
        except Exception:
            return None
        return None

    def codigo_cuenta(self, text: str, empresa=None, registro="COMPRA", use_llm=True, debug=False):
        candidates = self.retrieve(text, empresa=empresa, registro=registro, top_k=8)
        # Exact historical match is authoritative and should not be degraded by a 135M model.
        if candidates and candidates[0]["source"] == "historico" and candidates[0]["score"] >= 0.999:
            result = candidates[0]["pair"]
        else:
            result = self._ollama_choose(text, candidates) if use_llm else None
            result = result or self._fallback_pair(candidates)
        if debug:
            return result, candidates
        return result

    def responder(self, text: str, modo="auto", empresa=None, registro="COMPRA", use_llm=True) -> str:
        """Return codes only.

        - comprobante -> e.g. 01
        - identidad   -> e.g. 6
        - cuenta      -> e.g. 6365095|4212
        - auto        -> recognizes direct document/identity labels, otherwise treats input as glosa
        """
        modo = normalize(modo)
        if modo in {"COMPROBANTE", "DOCUMENTO", "TIPO COMPROBANTE"}:
            return self.codigo_comprobante(text)
        if modo in {"IDENTIDAD", "DOCUMENTO IDENTIDAD", "TIPO IDENTIDAD"}:
            return self.codigo_identidad(text)
        if modo in {"CUENTA", "GLOSA", "CONTABLE"}:
            return self.codigo_cuenta(text, empresa=empresa, registro=registro, use_llm=use_llm)

        c = self._catalog_lookup(text, self.comprobante_aliases)
        if c:
            return c
        i = self._catalog_lookup(text, self.identidad_aliases)
        if i:
            return i
        return self.codigo_cuenta(text, empresa=empresa, registro=registro, use_llm=use_llm)
