"""Minimal .xlsx reader using only Python's standard library.

It is intentionally read-only and supports the cell types used by the
Contasis workbooks in this project. No Excel installation is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def _col_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    out = 0
    for ch in letters:
        out = out * 26 + (ord(ch) - 64)
    return out - 1


def _xml_text(node) -> str:
    if node is None:
        return ""
    return "".join(t.text or "" for t in node.iter() if t.tag.endswith("}t"))


@dataclass
class SheetRef:
    name: str
    path: str


class XlsxReader:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._zip = zipfile.ZipFile(self.path)
        self.shared_strings = self._load_shared_strings()
        self.sheets = self._load_sheets()

    def close(self):
        self._zip.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _load_shared_strings(self):
        try:
            root = ET.fromstring(self._zip.read("xl/sharedStrings.xml"))
        except KeyError:
            return []
        vals = []
        for si in root.findall(f"{{{_NS_MAIN}}}si"):
            vals.append(_xml_text(si))
        return vals

    def _load_sheets(self):
        wb = ET.fromstring(self._zip.read("xl/workbook.xml"))
        rels = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        relmap = {}
        for rel in rels.findall(f"{{{_NS_REL_PKG}}}Relationship"):
            relmap[rel.attrib["Id"]] = rel.attrib["Target"]
        out = {}
        sheets = wb.find(f"{{{_NS_MAIN}}}sheets")
        for sh in sheets:
            name = sh.attrib["name"]
            rid = sh.attrib[f"{{{_NS_REL_DOC}}}id"]
            target = relmap[rid].replace("\\", "/")
            if target.startswith("/"):
                target = target.lstrip("/")
            elif not target.startswith("xl/"):
                target = "xl/" + target
            out[name] = SheetRef(name=name, path=target)
        return out

    def sheet_names(self):
        return list(self.sheets)

    def _resolve_sheet(self, sheet_name: str):
        if sheet_name in self.sheets:
            return self.sheets[sheet_name]
        wanted = sheet_name.strip().casefold()
        matches = [ref for name, ref in self.sheets.items() if name.strip().casefold() == wanted]
        if len(matches) == 1:
            return matches[0]
        raise KeyError(sheet_name)

    def iter_rows(self, sheet_name: str):
        sh = self._resolve_sheet(sheet_name)
        root = ET.fromstring(self._zip.read(sh.path))
        sheet_data = root.find(f"{{{_NS_MAIN}}}sheetData")
        if sheet_data is None:
            return
        for row in sheet_data.findall(f"{{{_NS_MAIN}}}row"):
            values = []
            for cell in row.findall(f"{{{_NS_MAIN}}}c"):
                ref = cell.attrib.get("r", "A1")
                idx = _col_index(ref)
                while len(values) <= idx:
                    values.append(None)
                ctype = cell.attrib.get("t")
                v = cell.find(f"{{{_NS_MAIN}}}v")
                raw = None if v is None else v.text
                if ctype == "s" and raw is not None:
                    try:
                        val = self.shared_strings[int(raw)]
                    except Exception:
                        val = raw
                elif ctype == "inlineStr":
                    val = _xml_text(cell.find(f"{{{_NS_MAIN}}}is"))
                elif ctype == "b":
                    val = raw == "1"
                elif ctype == "e":
                    val = raw
                elif ctype == "str":
                    val = raw or ""
                else:
                    if raw is None:
                        val = None
                    else:
                        try:
                            n = float(raw)
                            val = int(n) if n.is_integer() else n
                        except ValueError:
                            val = raw
                values[idx] = val
            yield int(row.attrib.get("r", "0")), values
