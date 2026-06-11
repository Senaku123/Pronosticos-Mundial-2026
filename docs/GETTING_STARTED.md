# GETTING_STARTED — de cero a datos cargados

> Guía reproducible (ES). Comandos e identificadores en inglés. Sigue estos pasos y obtienes
> **exactamente el mismo estado** verificado el 2026-06-11: entorno en verde + base de datos con
> ~49.475 partidos cargados. Referencia rápida de desarrollo: [`DEVELOPMENT.md`](DEVELOPMENT.md).

## 0. Requisitos

| Herramienta | Para qué | Notas |
|-------------|----------|-------|
| **Python 3.12** | runtime | pinneado en `.python-version` |
| **uv** | gestor de dependencias y entorno | se instala **global** (no en el repo) |
| **Docker** | PostgreSQL local | Docker Desktop corriendo |
| **DataGrip** | cliente de la base (opcional) | la base real es PostgreSQL, no DataGrip |

## 1. Instalar uv

```powershell
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reinicia la terminal (o añade `~/.local/bin` / `%USERPROFILE%\.local\bin` al PATH). Verifica:
`uv --version`.

> ¿No quieres uv? Alternativa con pip: `python -m venv .venv` → activar → `pip install -e .` +
> `pip install pytest ruff mypy`. uv es lo recomendado (lockfile reproducible y más rápido).

## 2. Entorno e instalación

Desde la raíz del repo:

```bash
uv sync            # crea .venv e instala desde uv.lock (entorno reproducible)
```

> `uv.lock` está commiteado: `uv sync` instala **exactamente** las mismas versiones. Si cambias
> dependencias en `pyproject.toml`, corre `uv lock` y commitea el `uv.lock` actualizado.

## 3. Verificar calidad (debe estar todo en verde)

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

Esperado: `All checks passed`, `Success: no issues found in 19 source files`, `14 passed`.

## 4. Base de datos (PostgreSQL en Docker)

```bash
cp .env.example .env            # Windows: Copy-Item .env.example .env  (ajusta el password)
docker compose up -d db         # levanta solo PostgreSQL (puerto 5432)
uv run alembic upgrade head     # crea el esquema (migraciones 0001 + 0002)
```

Verifica las tablas: `confederations`, `data_sources`, `ingestion_runs`, `matches`, `teams`,
`tournaments` (+ `alembic_version`).

### Conexión desde DataGrip (opcional)

| Campo | Valor (por defecto del `.env.example`) |
|-------|----------------------------------------|
| Host | `localhost` |
| Port | `5432` |
| Database | `wc26_forecast` |
| User | `wc26` |
| Password | `change_me` |

## 5. Cargar datos (snapshot inmutable + ingesta idempotente)

```bash
# Descarga results.csv a data/raw/martj42_results/<YYYY-MM-DD>/ con manifest + SHA-256
uv run python scripts/download_snapshots.py martj42_results

# Ingiere ese snapshot (valida con pandera y hace UPSERT idempotente)
uv run python scripts/ingest_results.py data/raw/martj42_results/<YYYY-MM-DD>/results.csv
```

(Reemplaza `<YYYY-MM-DD>` por la carpeta de fecha que creó la descarga.)

### Resultado esperado

```text
matches      = 49475   (el CSV trae 49477 filas; 2 son duplicados exactos y se omiten)
teams        = 336
tournaments  = 200
data_sources = 2
ingestion_runs = 1      (cada corrida queda registrada con su file_hash)
```

**Idempotencia:** vuelve a correr el mismo `ingest_results.py` → `matches` sigue en 49475 (cero
duplicados), y se añade otra fila en `ingestion_runs`. Es seguro re-ejecutar.

## 6. Qué se versiona y qué no

- **NO** en git (ver `.gitignore`): `data/raw|interim|processed` (datos pesados; se reconstruyen
  con su manifest+hash), `.venv`, `.env`.
- **SÍ** en git: código, docs, migraciones, `uv.lock`, y los `.gitkeep` que preservan la estructura.

## 7. Troubleshooting

- **`docker compose` falla:** Docker Desktop no está corriendo. Ábrelo y reintenta.
- **Puerto 5432 ocupado:** ya tienes un Postgres local. Cambia `POSTGRES_PORT` en `.env` (y el
  `DATABASE_URL`) a, p. ej., `5433`, y recrea el contenedor.
- **`alembic` no conecta:** revisa que `.env` exista y que `DATABASE_URL` apunte al host/puerto
  correctos; confirma `docker compose ps` (estado `healthy`).
- **Empezar de cero (borrar la BD):** `docker compose down -v` elimina el volumen; luego repite el
  paso 4.

## 8. Estado del proyecto

Fases implementadas: **Phase 1** (repo + reproducibilidad + esquema core) y **Phase 2** (ingesta +
gobernanza de datos). Siguiente: **Phase 3** (identidad temporal de equipos + `tournament_mapping`).
Detalle en [`PHASES.md`](PHASES.md).
