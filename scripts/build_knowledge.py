from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.xlsx_reader import XlsxReader

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data"

COMPROBANTES = {
"00":"OTROS","01":"FACTURA","02":"RECIBO DE HONORARIOS","03":"BOLETA DE VENTA",
"04":"LIQUIDACIÓN DE COMPRA","05":"BOLETO TRANS. AÉREO PASAJEROS","06":"BOLETO TRANS. AÉREO CARGA",
"07":"NOTA DE CRÉDITO","08":"NOTA DE DÉBITO","09":"GUIA DE REMISIÓN - REMITENTE",
"10":"RECIBO POR ARRENDAMIENTO","11":"PÓLIZA BOLSA DE VAL. PRODU OTR","12":"TICKET MAQUINA REGISTRADORA",
"13":"DOCUMENTO ENTIDADES FINANCIERA","14":"RECIBO SERV. PUBLICOS","15":"BOLETO TRANSP PUBLIC URBANO",
"16":"BOLETO DE VIAJE TRANSP PASAJER","17":"DOCUM IGLESIA CATÓLICA ARREND","18":"DOCUMENTO EMITIDO POR AFPs",
"19":"BOLETO EVENTOS PUBLICOS","20":"COMPROBANTE DE RETENCIÓN","21":"CONOC EMBARQU TRANS CARGA MARI",
"22":"COMPROB. OPER. NO HABITUALES","23":"PÓLIZA ADJUD REMATE VENTA MART","24":"CERTIF. PAGO REGALIA PERUPETRO",
"25":"DOCUMENTO DE ATRIBUCIÓN - IGV","26":"RECIB. SERV AGUA FINES AGRARIO","27":"SCTR - SEGUR COMPL TRAB RIESGO",
"28":"TARIF UNIFICADA USO AEROPUERTO","29":"DOCUM. EMITIDO POR COFOPRI","30":"DOC EMPR ADQUI TARJ CRED DEBIT",
"43":"BOL. AVIA COMER NO REGUL PASAJ","44":"BILLET DE LOTERÍA, RIFA Y APUE","45":"DOC EMIT CENT EDUC NO GRAYADOS",
"46":"FORMULARIO DE DECLARACIÓN YI","48":"COMPROBANTE DE OPERACIONES - LEY N° 29972",
"49":"CONSTANCIA DE DEPÓSITO - IVAP","50":"DECLARACION UNICA ADUANAS - ID","51":"PÓLIZA O DUI FRACCIONADA",
"52":"DESPACHO SIMPLIF. - IMPOR SIMP","53":"DECLARACIÓN MENSAJERIA COURIER","54":"LIQUIDACIÓN DE COBRANZA",
"55":"BVME TRANS FERROV PASAJEROS","56":"COMPROBANTE PAGO SEAE","87":"NOTA DE CRÉDITO ESPECIAL",
"88":"NOTA DE DÉBITO ESPECIAL","89":"NOTA DE AJUSTE DE OPERACIONES - LEY N° 29972","91":"COMPROBANTE DE NO DOMICILIADO",
"96":"EXCESO CRÉD FISC x RETIRO BIEN","97":"NOTA CRÉDITO - NO DOMICILIADO","98":"NOTA DÉBITO - NO DOMICILIADO",
"CH":"CHEQUE","DP":"DEPOSITO","LA":"LIBRO DE ACTAS","LE":"LETRA DE CAMBIO","LI":"LIQUIDACION"
}
IDENTIDAD = {
"0":"OTROS TIPOS DE DOCUMENTOS","1":"DNI / DOCUMENTO NACIONAL DE IDENTIDAD","4":"CARNET DE EXTRANJERIA",
"6":"RUC / REGISTRO ÚNICO DE CONTRIBUYENTES","7":"PASAPORTE","A":"CÉDULA DIPLOMÁTICA DE IDENTIDAD"
}


def code(v, pad=None):
    if v is None:
        return ""
    if isinstance(v, bool):
        s = str(v)
    elif isinstance(v, (int, float)):
        s = str(int(v)) if float(v).is_integer() else str(v)
    else:
        s = str(v).strip()
        if re.fullmatch(r"\d+\.0+", s):
            s = s.split(".")[0]
    s = s.strip()
    if pad and s.isdigit():
        s = s.zfill(pad)
    return s


def cell(row, idx):
    return row[idx] if idx < len(row) else None


def build_plan():
    path = RAW / "PLAN DE CUENTAS CONTASIS.xlsx"
    records = []
    with XlsxReader(path) as x:
        for rownum, row in x.iter_rows("PLAN DE CUENTAS"):
            if rownum == 1:
                continue
            acct = ""
            level = None
            for pos in (3, 2, 1):
                c = code(cell(row, pos))
                if c:
                    acct = c
                    level = {1: 1, 2: 2, 3: 3}[pos]
                    break
            desc = str(cell(row, 4) or "").strip()
            if not acct or not desc:
                continue
            records.append({
                "codigo": acct,
                "descripcion": desc,
                "nivel": level,
                "cuenta_balance": code(cell(row, 5)),
                "asiento_debe": code(cell(row, 6)),
                "asiento_haber": code(cell(row, 7)),
                "tipo": str(cell(row, 8) or "").strip(),
                "analisis": str(cell(row, 9) or "").strip(),
                "centro_costos": str(cell(row, 10) or "").strip(),
                "source_file": path.name,
                "source_sheet": "PLAN DE CUENTAS",
                "source_row": rownum,
            })
    return records


def add_history(out, path, company, sheet, registro, layout, plan_desc):
    if layout == "compra":
        ix = dict(doc=2, idt=6, idn=7, party=8, base=31, total=33, glosa=44)
    else:
        ix = dict(doc=2, idt=5, idn=6, party=7, base=27, total=29, glosa=38)
    with XlsxReader(path) as x:
        n = 0
        try:
            rows_iter = x.iter_rows(sheet)
        except KeyError:
            return 0
        for rownum, row in rows_iter:
            doc = code(cell(row, ix["doc"]), 2)
            idt = code(cell(row, ix["idt"]))
            base = code(cell(row, ix["base"]))
            total = code(cell(row, ix["total"]))
            glosa = str(cell(row, ix["glosa"]) or "").strip()
            if doc not in COMPROBANTES or not base or not total or not glosa:
                continue
            if idt and idt not in IDENTIDAD:
                continue
            out.append({
                "empresa": company,
                "registro": registro,
                "tipo_comprobante": doc,
                "tipo_comprobante_desc": COMPROBANTES.get(doc, ""),
                "tipo_identidad": idt,
                "tipo_identidad_desc": IDENTIDAD.get(idt, ""),
                "numero_identidad": code(cell(row, ix["idn"])),
                "razon_social": str(cell(row, ix["party"]) or "").strip(),
                "glosa": glosa,
                "cuenta_base": base,
                "cuenta_base_desc": plan_desc.get(base, ""),
                "cuenta_total": total,
                "cuenta_total_desc": plan_desc.get(total, ""),
                "source_file": path.name,
                "source_sheet": sheet,
                "source_row": rownum,
            })
            n += 1
        return n


def build_history(plan):
    desc = {r["codigo"]: r["descripcion"] for r in plan}
    out = []
    counts = {}
    rc = RAW / "RC CORPORACION 2026 OKI.xlsx"
    for sh in ["ENERO","FEBRERO","MARZO","ABRIL","MAYO","JUNIO","JULIO","AGOSTO"]:
        counts[f"RC/{sh}"] = add_history(out, rc, "RC CORPORACION", sh, "COMPRA", "compra", desc)
    joa = RAW / "RCV JOAQUISAN 062026.xlsx"
    counts["JOA/VENTAS"] = add_history(out, joa, "JOAQUISAN", "FORMATO_VENTAS", "VENTA", "venta", desc)
    counts["JOA/COMPRAS"] = add_history(out, joa, "JOAQUISAN", "FORMATO_ COMPRAS", "COMPRA", "compra", desc)
    est = RAW / "RCV NEGOCIACIONES ESTRADA 062026.xlsx"
    counts["EST/VENTAS"] = add_history(out, est, "NEGOCIACIONES ESTRADA", "FORMATO_VENTAS", "VENTA", "venta", desc)
    counts["EST/COMPRAS"] = add_history(out, est, "NEGOCIACIONES ESTRADA", "FORMATO_ COMPRAS", "COMPRA", "compra", desc)
    rv = RAW / "RV CORPORACION 2026.xlsx"
    for sh in ["ENERO","FEBRERO","MARZO","ABRIL","MAYO","JUNIO","JULIO"]:
        counts[f"RV/{sh}"] = add_history(out, rv, "RV CORPORACION", sh, "VENTA", "venta", desc)
    return out, counts



def _sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_csv(path: Path, rows):
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def build_source_manifest(plan_count, history_count):
    expected = [
        "PLAN DE CUENTAS CONTASIS.xlsx",
        "RC CORPORACION 2026 OKI.xlsx",
        "RCV JOAQUISAN 062026.xlsx",
        "RCV NEGOCIACIONES ESTRADA 062026.xlsx",
        "RV CORPORACION 2026.xlsx",
    ]
    docs = []
    for name in expected:
        path = RAW / name
        item = {"name": name, "exists": path.exists()}
        if path.exists():
            item["size_bytes"] = path.stat().st_size
            item["sha256"] = _sha256(path)
            try:
                with XlsxReader(path) as x:
                    item["sheets"] = x.sheet_names()
            except Exception as exc:
                item["read_error"] = str(exc)
        docs.append(item)
    return {
        "all_expected_sources_present": all(x["exists"] for x in docs),
        "source_documents": docs,
        "generated_records": {"plan_cuentas": plan_count, "historicos": history_count},
        "normalization_policy": (
            "Los XLSX originales se conservan sin cambios en data/raw. "
            "Las versiones limpias para RAG se generan en JSONL y CSV UTF-8 en data/normalized."
        ),
    }

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan = build_plan()
    history, counts = build_history(plan)
    with (OUT / "plan_cuentas.jsonl").open("w", encoding="utf-8") as f:
        for r in plan:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (OUT / "historicos.jsonl").open("w", encoding="utf-8") as f:
        for r in history:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "catalogos.json").write_text(json.dumps({"comprobantes": COMPROBANTES, "identidad": IDENTIDAD}, ensure_ascii=False, indent=2), encoding="utf-8")

    normalized = OUT / "normalized"
    _write_csv(normalized / "plan_cuentas.csv", plan)
    _write_csv(normalized / "historicos.csv", history)
    _write_csv(normalized / "catalogo_comprobantes.csv", [{"codigo": k, "descripcion": v} for k, v in COMPROBANTES.items()])
    _write_csv(normalized / "catalogo_identidad.csv", [{"codigo": k, "descripcion": v} for k, v in IDENTIDAD.items()])

    by_company = defaultdict(lambda: defaultdict(Counter))
    global_totals = defaultdict(Counter)
    for r in history:
        by_company[r["empresa"]][r["registro"]][r["cuenta_total"]] += 1
        global_totals[r["registro"]][r["cuenta_total"]] += 1
    defaults = {emp: {reg: cnt.most_common(1)[0][0] for reg, cnt in regs.items()} for emp, regs in by_company.items()}
    defaults["_GLOBAL"] = {reg: cnt.most_common(1)[0][0] for reg, cnt in global_totals.items()}
    (OUT / "account_total_defaults.json").write_text(json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = build_source_manifest(len(plan), len(history))
    manifest["by_source"] = counts
    manifest["account_total_defaults"] = defaults
    (OUT / "knowledge_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"plan_records": len(plan), "historical_records": len(history), "all_sources_present": manifest["all_expected_sources_present"], "by_source": counts, "defaults": defaults}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
