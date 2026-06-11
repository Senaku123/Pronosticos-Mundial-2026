# PHASES — World Cup 2026 Forecast Engine

> Desglose fase por fase (en español). Identificadores técnicos en inglés.
> Reglas vinculantes en [`METHODOLOGY_ADDENDUM.md`](METHODOLOGY_ADDENDUM.md).
> **Última actualización:** 2026-06-11 (secuencia reordenada por el addendum §16).

**Principio de orden:** datos y validación del motor **antes** que web. No se construye una web
grande antes de superar el go/no-go (addendum §4). La calibración va **antes** del simulador que la
consume. Cada fase indica: objetivo, entregables, archivos esperados, decisiones técnicas,
criterios de aceptación, riesgos y qué **NO** hacer todavía.

> La numeración refina la del prompt maestro original (0–12). Las fases nuevas/reordenadas existen
> para cumplir el addendum (gobernanza de datos, identidad de equipos, cutoff logic, calibración
> antes de simular, go/no-go, live scoring).

---

## Phase 0 — Research & project blueprint

- **Objetivo:** base documental y arquitectura; incorporar el addendum metodológico.
- **Entregables:** `PROJECT_BLUEPRINT.md`, `METHODOLOGY.md`, `BACKTESTING_STRATEGY.md`,
  `DATA_SOURCES.md`, `PHASES.md`, `METHODOLOGY_ADDENDUM.md`, `README.md`.
- **Archivos:** `docs/*`, `README.md`.
- **Decisiones técnicas:** idioma (docs ES, identificadores EN); reglas vinculantes del addendum.
- **Criterios de aceptación:** documentos coherentes entre sí; los 16 puntos del addendum
  trazables.
- **Riesgos:** documentación que no se respeta luego → mitigado con tests y criterios duros por
  fase.
- **NO hacer todavía:** código productivo; esquema SQL; ingesta.

## Phase 1 — Repo setup, reproducibility harness & incremental schema

> **Estado: implementada (2026-06-11).** Pendiente local: `uv lock` (generar/commitear lockfile) y
> `alembic upgrade head` contra una Postgres real.

- **Objetivo:** estructura del repo, entorno reproducible y primeras tablas (Alembic).
- **Entregables:** `pyproject.toml` con gestor único + **lockfile** + `requires-python`; `src/`
  instalable (src-layout); `src/utils` (config tipada con `pydantic-settings`, seeds, hashing);
  `docker-compose.yml` **solo PostgreSQL**; `.gitignore`, `.env.example`; Alembic inicializado;
  primeras migraciones (`teams`, `confederations`, `tournaments`, `matches`).
- **Archivos:** `pyproject.toml`, `alembic.ini`, `src/database/*`, `src/utils/*`,
  `docker-compose.yml`, `.gitignore`, `.env.example`.
- **Decisiones técnicas:** Alembic como única fuente de DDL; PK surrogate + UNIQUE natural + FKs.
- **Criterios de aceptación:** "instalación limpia desde lock reproduce el entorno";
  `alembic upgrade head` aplica limpio; CI mínimo (lint, type-check, pytest, validación de
  migraciones).
- **Riesgos:** reproducibilidad aparente → mitigado con lockfile + Python pinneado.
- **NO hacer todavía:** crear las 14+ tablas de golpe; React; Docker de la app.

## Phase 2 — Data ingestion, immutable snapshots & data governance

> **Estado: implementada (2026-06-11).** Código y migración listos; la ejecución real (descarga +
> `alembic upgrade head` + ingesta) se corre localmente con Postgres.

- **Objetivo:** ingerir fuentes con snapshots inmutables y trazabilidad.
- **Entregables:** `data_sources`, `ingestion_runs`; manifests con SHA-256; ingesta idempotente
  (UPSERT); validación con `pandera` en fronteras raw→interim→processed.
- **Archivos:** `src/data/*`, `scripts/ingest_*.py`, migraciones nuevas.
- **Decisiones técnicas:** `data/raw` fuera de git; política licencia upstream vs paquete; qué se
  versiona y qué no (addendum §14).
- **Criterios de aceptación:** re-ingesta no duplica; manifest con hash por fuente; validación
  aborta la pipeline ante datos inválidos.
- **Riesgos:** fuentes que cambian/desaparecen → snapshots pineados; fuente primaria + fallback.
- **NO hacer todavía:** features; modelos.

## Phase 3 — Team identity resolution & tournament mapping

> **Estado: implementada (2026-06-11).** Verificado: 200 tournaments mapeados (unmapped=0), 36
> aliases + 36 identity periods sembrados desde `former_names.csv` (idempotente). La colapsación
> física de la atribución histórica de partidos (p. ej. unir "West Germany" en "Germany") queda
> **diferida y documentada** como decisión backtesteable (addendum §10).

- **Objetivo:** identidad temporal de equipos y normalización de torneos.
- **Entregables:** `team_aliases`, `team_identity_periods`; `tournament_mapping` versionado
  (categorías `world_cup|continental_cup|qualifier|nations_league|friendly|other`); limpieza de
  nombres versionada.
- **Archivos:** `src/identity/*`, migraciones, seeds idempotentes.
- **Decisiones técnicas:** política de sucesión (Yugoslavia/Serbia, USSR/Russia, etc.) documentada
  y backtesteable (addendum §10).
- **Criterios de aceptación:** `test_unmapped_tournaments` pasa; ningún `match` con equipo sin
  identidad resuelta; sucesión documentada.
- **Riesgos:** atribución incorrecta de identidad → contamina Elo/forma → mitigado con tests.
- **NO hacer todavía:** features de fuerza.

## Phase 4 — Temporal cutoff logic, internal Elo & point-in-time feature store

> **Estado: implementada (2026-06-11).** Elo interno recalculado sobre 49.403 partidos jugados
> (98.806 ratings pre/post), corte estricto `match_date < cutoff`, lookup *as-of* y
> `test_no_future_leakage` (causalidad probada). Top activos plausibles (Spain, Argentina, France…).
> `rankings` (FIFA, serie bitemporal) queda como fuente externa opcional/posterior; en V1 la fuerza
> la da el Elo interno.

- **Objetivo:** mecánica anti-leakage (el corazón metodológico).
- **Entregables:** `elo_ratings` (Elo **interno** pre/post-match); `rankings` como serie bitemporal;
  feature store *as-of cutoff*; `test_no_future_leakage`.
- **Archivos:** `src/models/elo.py`, `src/features/*`, `tests/test_leakage.py`.
- **Decisiones técnicas:** fórmula de Elo (K-factor, margen, localía, tipo de partido) como
  hiperparámetro; lookup `effective_from <= cutoff_date` (addendum §1).
- **Criterios de aceptación:** `test_no_future_leakage` falla ante cualquier fecha posterior al
  cutoff; Elo usado por un partido es el **pre-match**.
- **Riesgos:** leakage silencioso → tests automáticos como gate.
- **NO hacer todavía:** modelo de marcadores.

## Phase 5 — Feature engineering

> **Estado: implementada (2026-06-11).** `match_features` construida sobre 49.403 partidos
> (día-atómica, leakage-safe): Elo home/away/diff, forma reciente (puntos y GF/GC últimos 5), días
> de descanso, importancia y sede; versionada con `feature_pipeline_version`/`cutoff_date`/
> `code_git_sha`. NULLs de forma/descanso solo en primeros partidos (141, documentado). Columnas
> finas de venue (altitud/calor) quedan reservadas para cuando haya datos.

- **Objetivo:** features de partido a partir del feature store.
- **Entregables:** `match_features` versionado (`feature_pipeline_version`, `cutoff_date`,
  `code_git_sha`); features de fuerza, forma, GF/GC, diferencia, tipo/importancia, sede
  (incluyendo candidatas de venue reservadas, addendum §13).
- **Archivos:** `src/features/*`, migraciones.
- **Criterios de aceptación:** features reproducibles con seed/cutoff; sin NaN no documentados;
  pasa `test_no_future_leakage`.
- **Riesgos:** colinealidad (Elo/FIFA/forma) → se documenta para SHAP.
- **NO hacer todavía:** ML challenger.

## Phase 6 — Baseline models

> **Estado: implementada (2026-06-11).** Tablas `model_runs` + `match_predictions`. Baselines
> `naive_favorite`, `elo_only`, `simple_poisson` (Elo→Poisson→matriz→W/D/L+marcador), predichos
> sobre los 49.403 partidos (148.209 predicciones). Primer pronóstico del Mundial 2026 (72 fixtures,
> con barra `tqdm`) generado. `fifa_ranking_baseline` diferido (sin datos de ranking FIFA).
> La evaluación formal (log loss/Brier/calibración) y el go/no-go son Phase 8.

- **Objetivo:** baselines obligatorios como piso de comparación.
- **Entregables:** `elo_only_baseline`, `fifa_ranking_baseline`, `simple_poisson_baseline`,
  `naive_favorite_baseline`; registrados como `model_runs`.
- **Archivos:** `src/models/baselines.py`.
- **Criterios de aceptación:** cada baseline produce W/D/L y se evalúa con las métricas estándar.
- **Riesgos:** ninguno mayor; son referencia.
- **NO hacer todavía:** declarar "éxito" sin comparar contra ellos.

## Phase 7 — Scoreline probability matrix (single source of truth) + calibration

- **Objetivo:** modelo de goles → matriz → W/D/L; capa de calibración.
- **Entregables:** Poisson/Dixon-Coles; `scoreline_probabilities`; derivación W/D/L por suma de
  zonas; calibración (Platt por defecto) validada temporalmente; `calibration_curves`;
  `test_wdl_single_source`.
- **Archivos:** `src/models/poisson.py`, `src/models/dixon_coles.py`,
  `src/models/calibration.py`, `tests/test_consistency.py`.
- **Decisiones técnicas:** **única fuente de verdad** (addendum §2); calibración **antes** del
  simulador.
- **Criterios de aceptación:** `test_wdl_single_source` pasa; calibración medida out-of-time
  (ECE/reliability con bandas).
- **Riesgos:** doble fuente de verdad → prohibida por diseño.
- **NO hacer todavía:** simulador; frontend.

## Phase 8 — Match-level backtesting + GO/NO-GO gate

- **Objetivo:** seleccionar modelo y validar contra baselines (criterio principal).
- **Entregables:** walk-forward expanding-window; métricas (log loss, Brier, RPS, calibración);
  skill score vs Elo-only; tests pareados (Diebold-Mariano/bootstrap); `backtest_runs`/
  `backtest_metrics`; **evaluación del go/no-go**.
- **Archivos:** `src/backtesting/match_level.py`, `src/evaluation/*`.
- **Decisiones técnicas:** selección estable a través de cutoffs; hold-out reciente intocado;
  corrección por comparaciones múltiples.
- **Criterios de aceptación (DURO):** el motor **supera a Elo-only** en Brier/Log Loss con
  calibración aceptable (addendum §4). Si no, se documenta y se itera; **no** se avanza a
  frontend/V2.
- **Riesgos:** sobreajuste al backtest → controles de §2.5 de `BACKTESTING_STRATEGY.md`.
- **NO hacer todavía:** frontend; V2; DL.

## Phase 9 — Challenger ML models

- **Objetivo:** evaluar si un modelo ML mejora las marginales de la matriz.
- **Entregables:** `challenger_model` (logistic/ordinal regularizada + **un** GBM); admisión solo
  si bate out-of-time de forma estable; si se admite, re-normaliza la matriz.
- **Archivos:** `src/models/challenger.py`, `feature_importances`.
- **Decisiones técnicas:** W/D/L como **ordinal**; sin ensembling; SHAP con nota de colinealidad.
- **Criterios de aceptación:** el challenger solo se promueve con evidencia (test pareado);
  consistencia mantenida.
- **Riesgos:** redundancia/overfitting → reducir arsenal (addendum, sobre-ingeniería).
- **NO hacer todavía:** tratar el challenger como fuente paralela.

## Phase 10 — Tournament simulation engine (Monte Carlo)

- **Objetivo:** simulador completo con realismo de formato 2026.
- **Entregables:** Monte Carlo (N ≥ 50k); `third_place_bracket_mapping`; resolución knockout
  (90'→ET→penales); desempates de grupos; persistencia **solo de agregados** (`simulation_results`)
  + `tournament_simulations` (seed, git_sha, data_hash, cutoff_date); `simulation_sample` opcional.
- **Archivos:** `src/simulation/*`, migraciones, tests deportivos.
- **Decisiones técnicas:** addendum §5/§6/§7/§9; error de Monte Carlo reportado; placeholders donde
  FIFA no confirme.
- **Criterios de aceptación:** `test_valid_bracket`, `test_no_draws_in_knockout`,
  `test_group_tiebreakers`, monotonía de P(fase), Σ P(champion)≈1.
- **Riesgos:** cruces inválidos / explosión de volumen → tests + solo agregados.
- **NO hacer todavía:** API/frontend.

## Phase 11 — Tournament-level backtesting (sanity check)

- **Objetivo:** validar el motor de propagación con Mundiales 2010–2022.
- **Entregables:** simulaciones históricas con cutoff; RPS de distribución de fase; block bootstrap
  por torneo; reporte de validez externa (32→48).
- **Archivos:** `src/backtesting/tournament_level.py`.
- **Decisiones técnicas:** **sanity check**, nunca selección (addendum §3); N=4 declarado.
- **Criterios de aceptación:** consistencia (campeones reales entre candidatos razonables);
  golden tests sintéticos del bracket.
- **Riesgos:** sobre-interpretar N=4 → comunicación explícita.
- **NO hacer todavía:** usar estos resultados para elegir modelo.

## Phase 12 — 2026 tournament simulation + live forecasting & scoring

- **Objetivo:** simular 2026 y operar durante el torneo.
- **Entregables:** simulación 2026 (probabilidades por fase y campeón con bandas); flujo de **live
  scoring** (publicar antes, puntuar después, re-simular rondas restantes con corte estricto);
  registro en `backtest_runs` (`backtest_level='live'`).
- **Archivos:** `scripts/run_2026_simulation.py`, `src/evaluation/live_scoring.py`.
- **Decisiones técnicas:** placeholders para clasificados/cruces no confirmados; corte estricto al
  publicar.
- **Criterios de aceptación:** probabilidades publicadas con timestamp y `model_run`; puntuación
  post-resultado contra baselines.
- **Riesgos:** inventar datos no confirmados → prohibido (placeholder).
- **NO hacer todavía:** prometer resultados; mezclar info posterior al corte de publicación.

## Phase 13 — FastAPI backend (gated)

- **Objetivo:** exponer el motor vía API (capa fina).
- **Entregables:** endpoints (`/health`, `/teams`, `/predict-match`, `/scoreline-matrix`,
  `/run-tournament-simulation`, `/tournament-probabilities`, `/backtest-results`,
  `/model-runs/{run_id}`); la API solo **lee** agregados precomputados.
- **Archivos:** `apps/api/*`.
- **Decisiones técnicas:** `apps/api` depende de `src/`, nunca al revés; sin cómputo pesado síncrono.
- **Criterios de aceptación:** contratos Pydantic; tests de endpoint; consistencia W/D/L.
- **Riesgos:** lógica filtrada a la capa de transporte → test que lo prohíba.
- **NO hacer todavía:** frontend si no hay valor claro.

## Phase 14 — React frontend (OPCIONAL, no-bloqueante)

- **Objetivo:** UI solo si el go/no-go se superó y hay valor.
- **Entregables:** pantallas mínimas (2–3 primero); comunicación honesta de incertidumbre; tipos TS
  generados desde OpenAPI.
- **Archivos:** `apps/web/*`.
- **Decisiones técnicas:** en V1 puede sustituirse por notebook/dashboard ligero.
- **Criterios de aceptación:** ninguna probabilidad sin banda/contexto de calibración.
- **Riesgos:** sobre-ingeniería → fase explícitamente opcional.
- **NO hacer todavía:** 9 pantallas de golpe.

## Phase 15 — Documentation, tests & GitHub polish

- **Objetivo:** dejar el repo público profesional y reproducible.
- **Entregables:** README final; cobertura de tests deportivos y de leakage; CI completo; guía de
  reproducción end-to-end.
- **Criterios de aceptación:** un tercero reproduce un `model_run`/`backtest_run` desde el lock + el
  snapshot.
- **NO hacer todavía:** prometer resultados; ocultar limitaciones.

---

## Mapa de dependencias (resumen)

```text
0 docs
1 repo+repro+schema
2 ingestion+governance
3 identity+mapping
4 cutoff+internal Elo+feature store   <- anti-leakage core
5 features
6 baselines
7 scoreline matrix + calibration      <- single source of truth
8 match-level backtesting + GO/NO-GO  <- gate
9 challenger ML (gated)
10 simulation engine
11 tournament-level backtesting (sanity check)
12 2026 simulation + live scoring
13 API (gated)
14 web (optional)
15 polish
```
