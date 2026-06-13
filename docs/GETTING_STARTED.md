# GETTING_STARTED — reproducción end-to-end (de cero a API + web)

> Guía reproducible (ES). Comandos e identificadores en inglés. Siguiendo estos pasos obtienes
> **el mismo estado verificado**: entorno en verde, base con ~49.475 partidos, motor calibrado que
> pasó el go/no-go, simulación 50k del Mundial 2026, y la API + el frontend funcionando.
> Referencia rápida de desarrollo: [`DEVELOPMENT.md`](DEVELOPMENT.md) · plan por fases:
> [`PHASES.md`](PHASES.md).

## 0. Requisitos

| Herramienta | Para qué | Notas |
|-------------|----------|-------|
| **Python 3.12** | runtime del motor | pinneado en `.python-version` |
| **uv** | gestor de dependencias y entorno | se instala **global** (no en el repo) |
| **Docker** | PostgreSQL local | Docker Desktop corriendo |
| **Node 22+** | frontend (Phase 14, opcional) | solo si vas a levantar `apps/web` |
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

## 2. Entorno e instalación

Desde la raíz del repo:

```bash
uv sync --all-groups   # crea .venv e instala TODO desde uv.lock (incluye dev + api)
```

> `uv.lock` está commiteado: instala **exactamente** las mismas versiones. `--all-groups` incluye
> el grupo `api` (FastAPI/uvicorn/httpx), necesario para la API y para que la suite de tests de la
> API corra. Si cambias dependencias en `pyproject.toml`, corre `uv lock` y commitea el `uv.lock`.

## 3. Verificar calidad (todo en verde)

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy            # usa la config: paquetes wc26 + wc26_api
uv run pytest
```

Esperado: `All checks passed`, `Success: no issues found in 51 source files`, `106 passed`.
Los tests que requieren base de datos se **saltan** automáticamente si no hay PostgreSQL
(la suite corre igual en CI sin BD).

## 4. Base de datos (PostgreSQL en Docker)

```bash
cp .env.example .env            # Windows: Copy-Item .env.example .env  (ajusta el password)
docker compose up -d db         # levanta solo PostgreSQL (puerto 5432)
uv run alembic upgrade head     # aplica TODAS las migraciones (0001 → 0010)
```

Conexión opcional desde DataGrip: host `localhost`, port `5432`, db `wc26_forecast`,
user `wc26`, password `change_me` (valores por defecto del `.env.example`).

## 5. Cargar datos (snapshot inmutable + ingesta idempotente)

```bash
uv run python scripts/download_snapshots.py martj42_results   # results.csv + manifest + SHA-256
uv run python scripts/ingest_results.py data/raw/martj42_results/<YYYY-MM-DD>/results.csv
```

Resultado esperado: `matches ≈ 49475`, `teams ≈ 336`, `tournaments = 200`. Re-ejecutar es seguro
(UPSERT idempotente: `matches` no crece; se añade una fila en `ingestion_runs`).

## 6. Pipeline de pronóstico (de datos crudos a probabilidades 2026)

Cada paso es un script idempotente; el orden importa (cada uno consume la salida del anterior).
Todos respetan el corte temporal anti-leakage (addendum §1).

```bash
# Phase 3 — identidad temporal + mapping de torneos
uv run python scripts/seed_identity.py data/raw/martj42_former_names/<YYYY-MM-DD>/former_names.csv

# Phase 4 — Elo interno pre/post por partido (corte estricto)
uv run python scripts/compute_elo.py

# Phase 5 — feature store point-in-time (requiere elo_ratings)
uv run python scripts/build_features.py

# Phase 6 — baselines (naive_favorite, elo_only, simple_poisson)
uv run python scripts/run_baselines.py

# Phase 7b — calibración Platt validada out-of-time (train <2018, test ≥2018)
uv run python scripts/calibrate_dc.py

# Phase 7 — forecast Dixon-Coles de los fixtures 2026 (matriz = única fuente de verdad)
uv run python scripts/forecast_dc.py

# Phase 8 — backtest match-level + veredicto GO/NO-GO (debe dar GO)
uv run python scripts/backtest_match_level.py

# Phase 11 — backtest tournament-level (sanity check, Mundiales 2010–2022)
uv run python scripts/backtest_tournament_level.py 50000

# Phase 10/12 — simulación oficial 2026: persiste el run "wc2026" (50k)
uv run python scripts/simulate_wc2026.py 50000
```

Salida esperada del último paso (las cifras exactas dependen del snapshot): el run **`wc2026`**
queda en `tournament_simulations`/`simulation_results` y se imprime la tabla de campeón —
del orden de **Spain ~20%, Argentina ~17%, France ~12%, Brazil ~7%, England ~6%**. El veredicto de
Phase 8 debe ser **GO** (el Dixon-Coles **calibrado** bate a Elo-only en log loss/Brier).

## 7. API (Phase 13)

La API lee agregados precomputados (el run `wc2026` debe existir, paso 6).

```bash
uv run --group api uvicorn wc26_api.main:app --reload
# docs interactivos: http://127.0.0.1:8000/docs
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/tournament-probabilities?stage=champion&limit=5"
```

## 8. Frontend (Phase 14, opcional)

Con la API y la BD corriendo:

```bash
npm --prefix apps/web install
npm --prefix apps/web run dev     # http://localhost:5173 (proxy /api → :8000)
```

Tres pantallas: probabilidades por selección/fase, predicción de partido y matriz de marcador,
cada una con su banda de incertidumbre y contexto de calibración.

## Atajo: levantar API + web con Docker (`run.bat`)

En vez de correr la API y el frontend nativos (pasos 7–8), podés levantar **todo el stack en
contenedores** con un solo comando. Requiere que la base ya tenga datos (pasos 4–6); el stack
reutiliza el mismo volumen de PostgreSQL.

```bat
run.bat            REM build + up: db + api + web
run.bat down       REM detener (la BD y su volumen se conservan)
run.bat logs       REM seguir logs
```

Servicios y puertos (configurables con `API_PORT` / `WEB_PORT`):

| Servicio | URL | Notas |
|----------|-----|-------|
| **web** | http://localhost:8095 | nginx sirve el build y proxya `/api` → api |
| **api** | http://localhost:8090/docs | FastAPI (solo lectura de agregados) |
| **db** | localhost:5432 | PostgreSQL (volumen `wc26_pgdata`) |

Definición: [`docker-compose.app.yml`](../docker-compose.app.yml) (capa sobre el
[`docker-compose.yml`](../docker-compose.yml) mínimo) + [`docker/`](../docker/) (Dockerfiles +
nginx). En contenedor, la API alcanza la base como `db:5432` (no `localhost`). Si la API responde
**503**, la base está vacía → corre el pipeline (pasos 5–6) apuntando a esa misma BD.

## 9. Operación diaria durante el torneo (Phase 12)

Orden estricto (publica ANTES, puntúa DESPUÉS, re-simula con corte estricto):

```bash
uv run python scripts/download_snapshots.py martj42_results
uv run python scripts/ingest_results.py data/raw/martj42_results/<YYYY-MM-DD>/results.csv
uv run python scripts/compute_elo.py
uv run python scripts/run_2026_simulation.py score      # puntúa lo publicado que ya tiene resultado
uv run python scripts/run_2026_simulation.py publish    # congela W/D/L de los próximos partidos
uv run python scripts/run_2026_simulation.py simulate    # re-simula rondas restantes (bandas MC)
```

## 10. Reproducibilidad (criterio de aceptación)

Un tercero reproduce cualquier corrida desde el **lockfile + el snapshot pineado**:

- **Entorno**: `uv sync --all-groups` instala versiones exactas (`uv.lock`).
- **Datos**: `data/raw/.../manifest.json` fija URL, fecha y **SHA-256**; el pipeline pinea el
  snapshot, no la fuente viva.
- **Metadata por corrida** (`NOT NULL`): cada `model_run` / `backtest_run` / `tournament_simulation`
  guarda `git_sha`, `cutoff_date`, `random_seed`, `python_version`, `config_json`, `created_at`.
- **Semillas**: la semilla se persiste por corrida; con la misma semilla, el motor reproduce
  resultados dentro de tolerancia. La simulación 2026 usa `seed = int(cutoff.strftime("%Y%m%d"))`.

## 11. Qué se versiona y qué no

- **NO** en git (`.gitignore`): `data/raw|interim|processed`, `.venv`, `.env`,
  `apps/web/node_modules`, `apps/web/dist`.
- **SÍ** en git: código, docs, migraciones, `uv.lock`, `apps/web/package-lock.json`, y los
  `.gitkeep` que preservan la estructura.

## 12. Troubleshooting

- **`docker compose` falla:** Docker Desktop no está corriendo.
- **Puerto 5432 ocupado:** cambia `POSTGRES_PORT` en `.env` (y `DATABASE_URL`) a `5433` y recrea el
  contenedor.
- **`alembic` no conecta:** revisa `.env` y `docker compose ps` (estado `healthy`).
- **API responde 503:** el run `wc2026` no existe todavía → corre el paso 6 (`simulate_wc2026.py`).
- **Frontend "API sin conexión":** la API no está en `:8000` → arráncala (paso 7).
- **Empezar de cero (borrar la BD):** `docker compose down -v` elimina el volumen; repite desde el
  paso 4.

## 13. Estado del proyecto

Fases **0–14 implementadas** (Phase 9 challenger ML diferida a V2). Restante: **Phase 15**
(pulido de docs/tests/CI). Detalle en [`PHASES.md`](PHASES.md).
