# Datos incluidos

## Fuentes originales (sin modificar)

Los archivos de `data/raw/` son copias byte-a-byte de los XLSX entregados por el usuario. Su integridad se verifica en `knowledge_manifest.json` mediante SHA-256.

- PLAN DE CUENTAS CONTASIS.xlsx
- RC CORPORACION 2026 OKI.xlsx
- RCV JOAQUISAN 062026.xlsx
- RCV NEGOCIACIONES ESTRADA 062026.xlsx
- RV CORPORACION 2026.xlsx

## Datos normalizados

Para evitar depender de nombres de hojas con espacios, formatos visuales de Excel o filas de encabezado, `scripts/build_knowledge.py` crea:

- `plan_cuentas.jsonl`: plan contable limpio para recuperación.
- `historicos.jsonl`: ejemplos reales con empresa, COMPRA/VENTA, comprobante, identidad, glosa, cuenta base y cuenta total.
- `normalized/*.csv`: las mismas fuentes derivadas en CSV UTF-8 con encabezados estables.
- `catalogos.json`: equivalencias exactas de comprobantes e identidad.
- `account_total_defaults.json`: cuenta total histórica predominante por empresa/tipo de registro.

Los originales nunca se sobrescriben.

### Nota sobre NEGOCIACIONES ESTRADA / compras

La hoja `FORMATO_ COMPRAS ` está presente en el XLSX, pero en el archivo entregado no contiene registros de compra completos con glosa + cuenta base + cuenta total; por eso aporta 0 ejemplos válidos al RAG. El archivo original sí queda íntegramente incluido.
