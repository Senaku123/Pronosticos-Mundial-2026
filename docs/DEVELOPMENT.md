# DEVELOPMENT — local setup

> Guía de entorno local (ES). Comandos e identificadores en inglés.
> Para la guía completa paso a paso (incluida la carga de datos y DataGrip), ver
> [`GETTING_STARTED.md`](GETTING_STARTED.md).

## Requisitos

- **Python 3.12** (pinneado en `.python-version`).
- **uv** como gestor único de dependencias y entornos — https://docs.astral.sh/uv/
- **Docker** (solo para levantar PostgreSQL local).
- **DataGrip** (opcional) como cliente de la base.

## Puesta en marcha

```bash
# 1) Copiar variables de entorno y ajustarlas
cp .env.example .env

# 2) Instalar dependencias desde el lockfile (crea .venv reproducible)
uv sync --all-groups

# 3) Levantar PostgreSQL local (solo la base; la app corre nativa)
docker compose up -d db

# 4) Aplicar el esquema
uv run alembic upgrade head

# 5) Verificar
uv run pytest
uv run ruff check .
uv run mypy src
```

> **Nota:** este repo aún no incluye `uv.lock`. Genéralo una vez con `uv lock` y **commitéalo**
> (la reproducibilidad declarada depende de él — ver `METHODOLOGY.md` §9). El paso 2 entonces
> instala exactamente las versiones pinneadas.

## Migraciones (Alembic)

- Alembic es la **única fuente de DDL**. Prohibido crear/alterar tablas a mano en DataGrip.
- La URL de la base se inyecta desde `wc26.utils.config` (no se guarda en `alembic.ini`).
- Crear una nueva revisión (autogenerate): `uv run alembic revision --autogenerate -m "mensaje"`.
- Revisar SIEMPRE el SQL autogenerado antes de aplicar.

## Estructura del paquete

El paquete instalable es `wc26` (en `src/wc26/`). Submódulos: `data`, `database`, `identity`,
`features`, `models`, `backtesting`, `simulation`, `evaluation`, `utils`. La capa `apps/api`
(FastAPI) y `apps/web` (React, opcional) dependen de `wc26`, nunca al revés.

## Reproducibilidad

Cada corrida importante persiste `git_sha`, `data_hash`, `cutoff_date`, `random_seed`,
`python_version` y `package_lock` (addendum §8). Las semillas se controlan vía
`wc26.utils.seeds`.
