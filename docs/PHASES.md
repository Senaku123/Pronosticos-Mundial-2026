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

> **Estado: implementada (2026-06-11).** **7a:** modelo **Dixon-Coles** (matriz con corrección τ;
> ρ=−0.037 por MLE). W/D/L por suma de zonas = **única fuente de verdad** (`test_wdl_single_source`
> puro y contra BD). `scoreline_probabilities` + forecast DC del Mundial. **7b:** **calibración Platt**
> validada **out-of-time** (train <2018, test ≥2018, n=8107): ECE 0.084→**0.021** (−75%), log loss
> 0.938→0.874, Brier 0.553→0.514. Tabla `calibration_curves`; runs `dixon_coles` (+`_calibrated`)
> sobre 49.403 partidos listos para Phase 8.

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

> **Estado: implementada (2026-06-11). VEREDICTO: GO ✅ (re-certificado tras auditoría).**
> Backtest **out-of-time de split único** (test ≥2018, n=8107; el walk-forward por-cutoff completo
> queda como refinamiento). ρ **y** Platt ajustados solo con <2018 (auditoría detectó y se corrigió
> un leakage de ρ; los números no cambiaron materialmente). `dixon_coles_calibrated` vs `elo_only`:
> log loss 0.873 vs 0.895, Brier 0.514 vs 0.522, RPS 0.171 vs 0.172, ECE 0.021 vs 0.046 — bootstrap
> pareado (con verificación de alineación de partidos): mean diff −0.021, CI [−0.026,−0.017],
> p=0.0000. **Dato clave:** el DC crudo NO supera a Elo-only (skill −0.049); **solo el calibrado**
> lo hace → valida la capa de calibración. Luz verde para frontend/V2.

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

> **Estado: DIFERIDA (decisión 2026-06-12).** El motor base (Dixon-Coles calibrado) ya superó el
> go/no-go de Phase 8 batiendo a Elo-only de forma estadísticamente significativa, por lo que un
> challenger ML **no es prerequisito** para la API ni la web. Se mantiene como opcional y *gated*:
> solo se incorporaría si bate las marginales de la matriz calibrada en log loss/Brier out-of-time
> **de forma estable a través de todos los cutoffs** (no en un solo split). Riesgo de
> sobre-ingeniería/colinealidad alto y beneficio incierto en V1 → se pospone a V2 (modelo
> consciente de jugadores), donde habrá señal nueva que justifique el arsenal. No se implementa
> `challenger.py` en V1.

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

> **Estado: implementada y endurecida por auditoría (2026-06-11).** Simulador Monte Carlo del
> Mundial 2026: 12 grupos con la cascada Article 13 **incluida la re-aplicación del head-to-head
> (Step 2)**; anfitriones (MEX/USA/CAN) con **ventaja de localía en fase de grupos** (knockout
> neutral, simplificación documentada); R32 con el bracket oficial (asignación de terceros que
> respeta restricciones — Annex C exacto pendiente; sin fallback inseguro); knockout
> 90'→prórroga **Dixon-Coles con ρ**→penales. El muestreo usa la **matriz calibrada (Platt)** —
> la configuración que ganó el GO — vía `calibrate_matrix` (zonas re-escaladas, única fuente de
> verdad intacta). **50.000 simulaciones** → `simulation_results`. **Fix (2026-06-12, Phase 12):**
> los partidos de **grupos** se muestreaban de la matriz **cruda** (solo el knockout recibía el
> calibrador); `simulate_group` ahora recibe el calibrador y la corrida oficial se regeneró.
> **P(campeón) (post-fix):** Spain 20.3%, Argentina 17.2%, France 12.3%, Brazil 6.9%,
> England 6.4% (la calibración des-comprime a los favoritos; alineado con mercados).

- **Objetivo:** simulador completo con realismo de formato 2026.
- **Entregables:** Monte Carlo (N ≥ 50k); `third_place_bracket_mapping`; resolución knockout
  (90'→ET→penales); desempates de grupos; persistencia **solo de agregados** (`simulation_results`)
  + `tournament_simulations` (seed, git_sha, cutoff_date, config_json); `simulation_sample` opcional.
- **Archivos:** `src/simulation/*`, migraciones, tests deportivos.
- **Decisiones técnicas:** addendum §5/§6/§7/§9; error de Monte Carlo reportado; placeholders donde
  FIFA no confirme.
- **Criterios de aceptación:** `test_valid_bracket`, `test_no_draws_in_knockout`,
  `test_group_tiebreakers`, monotonía de P(fase), Σ P(champion)≈1.
- **Riesgos:** cruces inválidos / explosión de volumen → tests + solo agregados.
- **NO hacer todavía:** API/frontend.

## Phase 11 — Tournament-level backtesting (sanity check)

> **Estado: implementada (2026-06-12). Sanity check superado ✅.** Formato 32 equipos
> (`structure32.py`: plantilla R16/QF/SF constante 2010–2022, verificada edición por edición) +
> motor `tournament32.py` reutilizando `simulate_group`/`resolve_knockout`; grupos hardcodeados
> **cross-validados contra `matches`** (un mismatch aborta; no se simula una estructura
> equivocada); etapa real inferida por conteo de partidos (final empatada → campeón registrado,
> asertado contra los finalistas). Corrida real (50k sims/edición, fit ρ+Platt estricto
> pre-torneo): RPS de fase 0,0943/0,1016/0,1097/0,1048 (2010/14/18/22), media **0,1026**
> [0,0969, 0,1076] (block bootstrap por torneo) vs **0,1271** del baseline `format_uniform` →
> skill **+0,19**; log loss de campeón 1,92 vs 3,47; **campeones reales en top-5 en las 4
> ediciones** (Spain #1, Germany #3, France #5, Argentina #2). `backtest_runs`
> (`tournament_level_v1`, level='tournament') + métricas. Limitaciones documentadas: cascada de
> desempate 2026 aplicada a ediciones históricas (diverge solo en empates exactos raros) y
> knockout neutral.

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

> **Estado: implementada (2026-06-12).** `run_2026_simulation.py` con tres flujos:
> **simulate** (re-simula las rondas restantes fijando resultados reales vía `KnownResults` —
> marcadores de grupo etiquetados por equipo y ganadores de knockout; empate de knockout sin
> ganador derivable se deja simulado con warning, nunca se adivina — y reporta **bandas de error
> Monte Carlo**), **publish** (congela W/D/L pre-partido del motor **y** del baseline Elo-only
> con el mismo Elo as-of de la fecha de publicación, como `model_runs` fechados e idempotentes;
> matriz calibrada = única fuente de verdad) y **score** (puntúa lo publicado contra el baseline
> con bootstrap pareado y lo registra en `backtest_runs` con `backtest_level='live'`; por partido
> puntúa la **última publicación ≤ día del partido** — leakage-safe porque el lookup as-of es
> estrictamente anterior). Verificado end-to-end el 2026-06-12: 70 fixtures publicados (los del
> 11-jun ya iniciados se excluyen, no se "publica" el pasado), re-simulación 50k con 0 resultados
> fijados (snapshot upstream aún sin los partidos del 11-jun, hash idéntico verificado) → Spain
> 20,6% ±0,4. Configuración del motor (ρ + Platt) = fit pre-torneo que ganó el GO, persistida en
> `config_json`. Operación diaria: download → ingest → compute_elo → score → publish → simulate.
>
> **Auditoría adversarial post-implementación (2026-06-12): 15 hallazgos confirmados, todos
> corregidos.** Los serios: (1) un empate de semifinal (definido por penales) con el partido por
> el 3.er puesto ya jugado hacía que la inferencia "aparece en un partido posterior" fijara al
> **PERDEDOR** como finalista — el 3.er puesto ahora se excluye de la inferencia y nunca es hecho
> condicionante (tests de regresión en las tres ventanas temporales); (2) como la asignación de
> terceros no es el Annex C oficial, los resultados reales del R32 podían **no coincidir nunca**
> con el pareo simulado y descartarse en silencio — ahora los cruces reales del R32 (jugados o
> programados) **fijan** los slots de terceros (`thirds_from_real_pairings` + `assign_thirds` con
> slots pineados) y todo resultado conocido no consumido por la simulación **lanza error** en vez
> de ignorarse. Menores: configuración del motor serializada una sola vez (`engine_config_json`,
> precisión completa) y **releída** del run oficial en vez de re-ajustarse en cada comando
> (~14 s → instantáneo); helpers únicos (`outcome_index`, `per_match_log_loss`,
> `evaluation_metric_rows`, `wc26.utils.provenance.git_sha`, `world_cup_matches` parametrizada
> compartida con Phase 11); `publish` reporta `[warn]` los fixtures pasados sin resultado;
> `score` sin partidos ya no persiste métricas en cero; barras de progreso reales. 90 tests.

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

> **Estado: implementada (2026-06-12).** Capa fina `wc26_api` en `apps/api/` (depende de `src/`,
> nunca al revés; test `test_src_does_not_import_api` lo verifica). Endpoints: `GET /health`
> (liveness + conectividad BD + run congelado disponible), `GET /teams` + `GET /teams/{id}`
> (Elo as-of opcional), `POST /predict-match` y `GET /scoreline-matrix` (única matemática por
> request: **una** matriz Dixon-Coles **calibrada**; W/D/L sumada de zonas = única fuente de
> verdad, `truncated_mass` explícito), `GET /tournament-probabilities` + `GET /tournament-simulations`
> + `POST /run-tournament-simulation` (**solo lectura** de agregados precomputados; la API nunca
> simula 50k síncronamente), `GET /backtest-results` y `GET /model-runs/{id}`. El motor congelado
> (ρ + Platt) se **relee** del run oficial `wc2026`; si no está, los endpoints de motor devuelven
> **503** en vez de re-ajustar (pesado). Grupo de dependencias `api` (fastapi/uvicorn/httpx);
> 16 tests herméticos con SQLite en memoria (sin Postgres) cubren todos los endpoints, la
> consistencia W/D/L y la dirección de dependencia. Levantar:
> `uv run --group api uvicorn wc26_api.main:app --reload`.

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

> **Estado: implementada (mínima, 2026-06-12).** SPA React + Vite + TypeScript en `apps/web/`
> (depende de la API, nunca al revés). **3 pantallas** (no 9): (1) **Probabilidades** por selección
> y fase (ordenable; el campeón se muestra con su **banda de error Monte Carlo 95%** y el contexto
> de calibración), (2) **Predicción de partido** (W/D/L calibrado + goles esperados + marcadores
> más probables, con datalist de equipos), (3) **Matriz de marcador** (heatmap + marginales +
> `truncated_mass` explícito). Cliente `fetch` tipado contra los contratos de la API; en dev,
> proxy de Vite `/api → :8000` (sin CORS). **Comunicación honesta de incertidumbre** en cada vista
> + pie permanente (calibración Platt, banda MC, formato 48 sin análogo histórico, no es asesoría
> de apuestas). `npm run build` (tsc estricto + vite) verde; verificado end-to-end contra
> API+Postgres reales (Spain 20.3 %, Argentina 17.2 %). Tipos hand-written con script
> `npm run gen:types` para regenerarlos desde OpenAPI. Levantar:
> `npm --prefix apps/web install && npm --prefix apps/web run dev` (con la API y la BD activas).

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
