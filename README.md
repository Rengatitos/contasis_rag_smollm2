# Contasis RAG + FastAPI + Ollama SmolLM2 135M

Proyecto Docker para devolver **únicamente códigos Contasis** a partir de tipos de documento, tipos de identidad o glosas contables.

## Arquitectura

```text
Cliente / Notebook
       |
       | HTTP :8000
       v
  FastAPI (api)
       |
       +--> catálogos exactos
       +--> RAG histórico + Plan Contasis
       |
       v
 Ollama :11434
 smollm2:135m
       |
       v
 código validado
```

SmolLM2 no genera cuentas libremente. Primero el RAG recupera cuentas que **sí existen** en los documentos y el modelo solo puede seleccionar entre esos candidatos. Si intenta devolver otro código, se rechaza su salida.

## Documentos incluidos

Los 5 XLSX originales están preservados sin modificación en `data/raw/`:

1. `PLAN DE CUENTAS CONTASIS.xlsx`
2. `RC CORPORACION 2026 OKI.xlsx`
3. `RCV JOAQUISAN 062026.xlsx`
4. `RCV NEGOCIACIONES ESTRADA 062026.xlsx`
5. `RV CORPORACION 2026.xlsx`

No se reemplazan los originales. `scripts/build_knowledge.py` genera formatos más limpios para el RAG:

- `data/plan_cuentas.jsonl`
- `data/historicos.jsonl`
- `data/catalogos.json`
- `data/account_total_defaults.json`
- `data/normalized/plan_cuentas.csv`
- `data/normalized/historicos.csv`
- `data/normalized/catalogo_comprobantes.csv`
- `data/normalized/catalogo_identidad.csv`
- `data/knowledge_manifest.json`

El manifest contiene SHA-256, tamaño y hojas de cada XLSX, más los conteos generados.

## Levantar todo

Requisito: Docker Desktop abierto y funcionando, con Docker Compose disponible. No es necesario instalar ni ejecutar Ollama directamente en Windows: el proyecto lo levanta dentro de Docker.

### Primer arranque

Desde la raíz del proyecto:

```powershell
docker compose down
docker compose up --build
```

El primer arranque puede tardar varios minutos. Docker construye las imágenes, inicia Ollama, descarga `smollm2:135m` y crea el modelo restringido `contasis-smollm2` usando el `Modelfile`.

Mantén abierta esa terminal. El sistema estará listo cuando `model-init` termine con código `0`, la API indique que escucha en el puerto `8000` y Jupyter indique que escucha en el puerto `8888`.

Para arranques posteriores ya no hace falta reconstruir las imágenes:

```powershell
docker compose up
```

Servicios accesibles desde Windows:

- API Contasis: `http://localhost:8000`
- Swagger / OpenAPI: `http://localhost:8000/docs`
- Jupyter Lab: `http://localhost:8888`

Ollama escucha en el puerto `11434` únicamente dentro de la red de Docker. La API lo consulta mediante `http://ollama:11434`; no se publica ese puerto en Windows para evitar conflictos con una instalación local de Ollama.

### Comprobar que funciona

Abre otra terminal PowerShell y consulta el estado:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Después prueba el RAG:

```powershell
Invoke-RestMethod "http://localhost:8000/v1/codigo?texto=factura"
```

La respuesta esperada es:

```text
01
```

Para ver el estado de los contenedores o revisar sus registros:

```powershell
docker compose ps
docker compose logs -f
```

Para detener y retirar los contenedores:

```powershell
docker compose down
```

### Problema: el puerto 11434 ya está ocupado

Si una versión anterior de `docker-compose.yml` muestra el error `ports are not available` para el puerto `11434`, significa que Ollama ya se está ejecutando en Windows. La configuración actual evita el conflicto porque no publica ese puerto. El servicio `ollama` debe verse así:

```yaml
ollama:
  image: ollama/ollama:latest
  restart: unless-stopped
  volumes:
    - ollama_data:/root/.ollama
```

Después de corregir una configuración anterior, reinicia el conjunto:

```powershell
docker compose down
docker compose up
```

## API

### POST /v1/codigo

Devuelve **text/plain** con el código y nada más.

Factura:

```bash
curl -X POST http://localhost:8000/v1/codigo \
  -H "Content-Type: application/json" \
  -d '{"texto":"registro de una factura","modo":"auto"}'
```

Respuesta:

```text
01
```

Glosa:

```bash
curl -X POST http://localhost:8000/v1/codigo \
  -H "Content-Type: application/json" \
  -d '{"texto":"SERVICIO DE INTERNET 993630309","modo":"cuenta","empresa":"RC CORPORACION","registro":"COMPRA"}'
```

Respuesta:

```text
6365095|4212
```

Convención para glosas:

```text
CUENTA_BASE|CUENTA_TOTAL
```

También existe `GET /v1/codigo?texto=factura` para pruebas rápidas.

## Ejemplos verificados

```text
factura                                      -> 01
boleta                                       -> 03
RUC                                          -> 6
DNI                                          -> 1
SERVICIO DE INTERNET 993630309               -> 6365095|4212
ENERGIA ELECTRICA JR.1RO DE NOVIEMBRE        -> 6361095|4212
ENERGIA ELECTRICA JR.LOS INCAS               -> 6361095|4212
ENERGIA ELECTRICA JR.FCO.IRAZOLA              -> 6361095|4212
```

## Notebook

`notebooks/Contasis_RAG_SmolLM2.ipynb` consume la API por HTTP. Dentro de Docker utiliza `http://api:8000`; fuera de Docker usa `http://localhost:8000`.

Por tanto, el notebook prueba el mismo camino que utilizará una aplicación externa, en vez de saltarse la API.

## Desplegar el RAG gratuito en Render

El despliegue gratuito usa solamente **FastAPI + RAG**. No inicia Ollama ni Jupyter y establece `use_llm=false` como valor predeterminado para ajustarse mejor a los recursos de Render Free. La ejecución local con Docker Compose conserva SmolLM2 habilitado.

Archivos específicos del despliegue:

- `render.yaml`: define el Web Service gratuito.
- `Dockerfile.render`: construye una imagen reducida y escucha en el puerto indicado por Render.
- `requirements-render.txt`: excluye Jupyter y las dependencias que no necesita la API publicada.

### 1. Subir el proyecto a GitHub

Crea un repositorio y sube el proyecto completo. Los archivos generados de conocimiento que deben estar incluidos son:

```text
data/catalogos.json
data/account_total_defaults.json
data/historicos.jsonl
data/plan_cuentas.jsonl
```

### 2. Crear el servicio en Render

1. Ingresa a `https://dashboard.render.com` y conecta tu cuenta de GitHub.
2. Selecciona **New → Blueprint**.
3. Escoge el repositorio del proyecto.
4. Render detectará `render.yaml` y propondrá el servicio `contasis-rag-api` con el plan Free.
5. Confirma con **Apply** y espera a que finalice la construcción.

No uses `docker-compose.yml` en Render: ese archivo corresponde al entorno local completo con Ollama y Jupyter.

### 3. Probar la URL pública

Render asignará una dirección parecida a:

```text
https://contasis-rag-api.onrender.com
```

Comprueba el estado:

```powershell
Invoke-RestMethod https://contasis-rag-api.onrender.com/health
```

Prueba una consulta:

```powershell
Invoke-RestMethod "https://contasis-rag-api.onrender.com/v1/codigo?texto=factura"
```

Prueba una glosa indicando explícitamente que no debe usar LLM:

```powershell
$body = @{
    texto = "SERVICIO DE INTERNET 993630309"
    modo = "cuenta"
    empresa = "RC CORPORACION"
    registro = "COMPRA"
    use_llm = $false
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "https://contasis-rag-api.onrender.com/v1/codigo" `
    -ContentType "application/json" `
    -Body $body
```

La primera petición después de un periodo sin uso puede tardar mientras Render reactiva el servicio gratuito. El sistema utilizará el mejor candidato recuperado por el RAG y nunca intentará conectarse con Ollama si se mantiene `use_llm=false`.

## Reconstruir el RAG

Después de cambiar/agregar históricos en `data/raw/`:

```bash
python scripts/build_knowledge.py
```

Reinicia la API para reconstruir el índice en memoria:

```bash
docker compose restart api
```

## Validación

```bash
python tests/test_rag.py
python tests/test_api.py
```

`test_api.py` comprueba la API sin depender de Ollama para las coincidencias determinísticas (`use_llm=false`). Para glosas nuevas, `use_llm=true` hace que la API consulte a Ollama.
