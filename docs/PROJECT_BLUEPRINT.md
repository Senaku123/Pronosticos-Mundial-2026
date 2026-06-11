# PROJECT_BLUEPRINT — World Cup 2026 Forecast Engine

> **Documento core del proyecto** (en español). Es la guía fase por fase.
> Todos los identificadores técnicos (carpetas, archivos, variables, funciones, clases, tablas,
> columnas, endpoints, ramas) están en **inglés** y son canónicos.
>
> **Documentos relacionados:** [`METHODOLOGY_ADDENDUM.md`](METHODOLOGY_ADDENDUM.md) (reglas
> vinculantes), [`METHODOLOGY.md`](METHODOLOGY.md), [`BACKTESTING_STRATEGY.md`](BACKTESTING_STRATEGY.md),
> [`DATA_SOURCES.md`](DATA_SOURCES.md), [`PHASES.md`](PHASES.md).
>
> **Última actualización:** 2026-06-11 (incorpora el addendum metodológico obligatorio v1).

---

## 1. Visión

Construir un **motor probabilístico de pronósticos** para el Mundial de Fútbol 2026, serio,
modular, reproducible y explicable. El motor debe:

- predecir partidos individuales (W/D/L, goles esperados, matriz de marcadores);
- simular el torneo completo por Monte Carlo para estimar probabilidades de clasificación por fase
  y de campeón.

**Principio rector (anti-humo):** ninguna afirmación de calidad sin medición. Toda probabilidad va
acompañada de su evaluación contra baselines, su calibración y su incertidumbre. El proyecto no
promete "predecir el Mundial"; promete un motor honesto, evaluable y reproducible.

---

## 2. Alcance

### 2.1 Enfoque por versiones

- **V1 — National team forecasting engine (foco actual).** Solo selecciones nacionales. Sin datos
  de clubes. Sin odds de apuestas. Features: resultados históricos internacionales, **Elo
  recalculado internamente**, FIFA ranking (opcional, como serie temporal y baseline), forma
  reciente, GF/GC, diferencia de goles, tipo/importancia de partido, sede (local/visitante/neutral
  y candidatas de venue), confederación, ciclos mundialistas.
- **V2 — Player-aware model (futuro).** Señales de jugador/plantilla (edad media, caps, continuidad,
  minutos, top-5 leagues, etc.). Los datos de clubes solo miden forma/calidad/disponibilidad de
  jugadores; **nunca** se mezclan resultados de clubes con selecciones.
- **V3 — Advanced analytics / DL (futuro, condicionado).** Solo si hay volumen y datos de eventos
  (xG, pases, embeddings, grafos). No se usa DL en V1.

### 2.2 Objetivos funcionales del motor

`p_team_a_win`, `p_draw`, `p_team_b_win`; goles esperados por equipo; matriz de marcadores;
marcadores más probables; probabilidades por fase (Round of 32, Round of 16, Quarterfinal,
Semifinal, Final, Champion).

### 2.3 Fuera de alcance (por ahora)

Cloud deployment; datos de clubes en V1; odds de apuestas en V1; deep learning en V1; StatsBomb en
V1.

---

## 3. Reglas vinculantes (resumen del addendum)

El detalle está en [`METHODOLOGY_ADDENDUM.md`](METHODOLOGY_ADDENDUM.md). Resumen ejecutivo:

1. **Anti-leakage:** Elo recalculado internamente; rankings como series bitemporales; ningún
   feature posterior al `cutoff_date`; tests de leakage.
2. **Única fuente W/D/L:** matriz Poisson/Dixon-Coles; W/D/L por suma de zonas; ML solo como
   `challenger_model`.
3. **Selección a nivel partido**, no por campeón; tournament-level es sanity check.
4. **Go/no-go:** superar a Elo-only en Brier/Log Loss antes de frontend/V2.
5. **Knockout sin empates:** 90' → extra time → penalties.
6. **Bracket R32 oficial:** `third_place_bracket_mapping` versionado.
7. **Desempates de grupos** según reglamento oficial verificado.
8. **Reproducibilidad mecanizada:** metadata `NOT NULL` por corrida.
9. **No** persistir simulaciones crudas; solo agregados.
10. **Identidad temporal de equipos** (`team_identity_periods`).
11. **Tournament mapping** versionado.
12. **Shrinkage** para equipos con poca data (roadmap).
13. **Venue/altitud/calor** como features candidatas.
14. **StatsBomb/licencias** respetadas (V2/V3).
15. **Sin odds** en V1.
16. **Fases reordenadas:** datos y validación antes que web.

---

## 4. Arquitectura del repositorio

```text
worldcup-2026-forecast-engine/
├── apps/
│   ├── api/                # FastAPI (capa fina de transporte; depende de src/, nunca al revés)
│   └── web/                # React + Vite (OPCIONAL, no-bloqueante; sólo tras el go/no-go)
├── data/
│   ├── raw/                # snapshots inmutables (gitignored; versionados por manifest+hash)
│   ├── interim/            # zona de trabajo (gitignored)
│   └── processed/          # entrada estable a features/modelos (regenerable, gitignored)
├── docs/
├── notebooks/              # solo exploración; no lógica productiva
├── src/
│   ├── data/               # ingestion + snapshots
│   ├── database/           # SQLAlchemy models + Alembic
│   ├── identity/           # team identity resolution + tournament mapping
│   ├── features/           # feature store point-in-time (as-of cutoff)
│   ├── models/             # elo, poisson/dixon-coles, baselines, challenger ML, calibration
│   ├── backtesting/        # match-level + tournament-level
│   ├── simulation/         # Monte Carlo, bracket, knockout resolution, tiebreakers
│   ├── evaluation/         # scoring rules, calibration, reporting
│   └── utils/              # config, seeds, hashing, reproducibility
├── tests/
├── scripts/
├── README.md
├── pyproject.toml
├── alembic.ini
├── docker-compose.yml      # mínimo: solo PostgreSQL + volumen persistente
└── .env.example
```

**Regla de dependencia:** `apps/api` y `apps/web` dependen de `src/`, nunca al revés. Los endpoints
solo validan entrada, llaman a un *service* de `src/` y serializan salida. La lógica de
predicción/simulación vive en `src/` para que notebooks, scripts y tests la reutilicen.

**Packaging:** `src/` es un paquete instalable (src-layout, modo editable). Gestor único de
dependencias con lockfile y `requires-python` fijo (ver `METHODOLOGY.md` §reproducibilidad).

---

## 5. Base de datos (PostgreSQL)

PostgreSQL local es la base real; DataGrip es solo cliente de administración/visualización. El
esquema se construye **incrementalmente por fase** vía Alembic (no las 14+ tablas de golpe), y se
trata como hipótesis revisable. Todo DDL pasa por Alembic; **prohibido** DDL manual en DataGrip.

### 5.1 Identidad y catálogos

- `teams` — entidad federativa estable (surrogate PK).
- `team_aliases` — `(source_name, raw_name, team_id, mapping_version)` para reconciliar fuentes.
- `team_identity_periods` — `(team_id, name, fifa_code, country, valid_from, valid_to)`; sucesión
  histórica (Yugoslavia/Serbia, USSR/Russia, Czechoslovakia/Czech Republic, Czech Republic/Czechia,
  Macedonia/North Macedonia). Ver addendum §10.
- `confederations` — catálogo (UEFA, CONMEBOL, CONCACAF, CAF, AFC, OFC).
- `tournaments` — torneos concretos.
- `tournament_mapping` — texto libre → categoría limpia; columnas `tournament_category`,
  `match_importance_weight`, `confederation_scope`, `is_official`, `source`, `mapping_version`.
  Categorías: `world_cup`, `continental_cup`, `qualifier`, `nations_league`, `friendly`, `other`.
  Ver addendum §11.

### 5.2 Hechos históricos

- `matches` — partidos jugados. UNIQUE natural `(home_team_id, away_team_id, match_date,
  tournament_id)`. FK a `teams`, `tournaments`. Lleva `source_id`/`ingestion_run_id`.
- `match_types` — categoría y peso por tipo (peso asociado a `model_run`, no global).

### 5.3 Ratings y rankings (series temporales bitemporales — anti-leakage)

- `elo_ratings` — Elo **recalculado internamente**; pre-match y post-match por partido para
  auditar. Columnas de vigencia (`as_of_date`/`effective_from`). UNIQUE `(team_id, as_of_date,
  source)`.
- `rankings` — rankings externos (p. ej. FIFA) como serie: `(team_id, publication_date,
  effective_from, effective_to, source_name, source_version, data_hash, value)`. Lookup *as-of*
  `effective_from <= cutoff_date`. Ver addendum §1.

### 5.4 Gobernanza de datos

- `data_sources` — catálogo: `name`, `url`, `license`, `upstream_source`, `upstream_license`,
  `tos_notes`.
- `ingestion_runs` — `source_id`, `snapshot_date`, `file_hash`, `row_count`, `started_at`,
  `status`.

### 5.5 Features

- `match_features` — un registro por partido/feature-set; lleva `feature_pipeline_version`,
  `cutoff_date`, `code_git_sha`. Construido siempre *as-of cutoff*.
- Columnas candidatas de venue **reservadas** (nullable/opcionales en V1; addendum §13):
  `venue_country`, `venue_city`, `is_host_team`, `is_home_region`, `venue_altitude`,
  `temperature_bucket`, `travel_distance_proxy`.

### 5.6 Modelos y predicciones

- `model_runs` — corrida de modelo (incluye baselines). Metadata reproducibilidad **`NOT NULL`**:
  `run_id`, `model_name`, `model_version`, `git_sha`, `data_hash`, `cutoff_date`, `random_seed`,
  `python_version`, `package_lock`, `config_json`, `created_at`. Ver addendum §8.
- `match_predictions` — W/D/L (derivado de la matriz) y goles esperados por partido/`model_run`.
- `scoreline_probabilities` — matriz de marcadores por partido "oficial" (no por iteración Monte
  Carlo). Ver addendum §9.
- `calibration_curves` — reliability curves y parámetros de calibración por `model_run`.
- `feature_importances` — importancias por `model_run` (con nota sobre colinealidad).

### 5.7 Simulación (solo agregados)

- `tournament_simulations` — metadata de corrida: `simulation_id`, FK `model_run_id`, `random_seed`,
  `number_of_simulations`, `git_sha`, `data_hash`, `cutoff_date`, `created_at` (**`NOT NULL`**).
  Hereda `model_name`, `model_version`, `python_version`, `package_lock` vía el FK `model_run_id`
  (que es `NOT NULL`). Ver addendum §8/§9.
- `simulation_results` — **agregados** por equipo/fase: `stage_probability` (Round of 32 … Champion),
  `group_qualification_probability`, con su error de Monte Carlo. PK lógica
  `(tournament_simulation_id, team_id, stage)`. `champion_probability` es un **derivado/vista** de
  `stage_probability` con `stage = 'Champion'` (no se duplica el dato).
- `simulation_sample` — (opcional) muestra pequeña de simulaciones completas para debugging, con
  seed fijo. **No** se persisten millones de partidos simulados.

### 5.8 Estructura del torneo 2026

- `tournament_format` — reglas del torneo: `n_teams`, grupos, clasificación, y
  `group_tiebreaker_rules` (cascada de desempates) con `mapping_version` (artefacto versionado).
  Cascada de grupos **verificada** (FIFA WC 2026, Article 13): puntos → head-to-head (puntos/DG/goles
  entre empatados) → DG global → goles global → team conduct score (disciplina) → ranking FIFA
  (sin sorteo). Detalle en `METHODOLOGY_ADDENDUM.md` §7. Test: `test_group_tiebreakers`.
- `groups`, `group_slots` — los 12 grupos y sus plazas.
- `scheduled_matches` — partidos programados/hipotéticos del torneo (separados de `matches`
  históricos para evitar confusión y leakage).
- `third_place_bracket_mapping` — las **495 combinaciones** oficiales (Annex C) de terceros → slots
  de R32 (Match 73–88), versionado. Ver addendum §6.

### 5.9 Backtesting

- `backtest_runs` — metadata reproducibilidad (igual que `model_runs`), `backtest_level`
  (`match` | `tournament`), `cutoff_date`.
- `backtest_metrics` — métricas por corrida (log loss, brier, rps, ece, accuracy, skill score
  vs baseline, etc.).

> **Claves/constraints:** cada tabla define PK surrogate + UNIQUE natural de deduplicación + FKs con
> `ON DELETE` explícito, para garantizar idempotencia e integridad. Sin esto, "reproducible" es
> retórica.

---

## 6. Estrategia de modelado (resumen)

Detalle en [`METHODOLOGY.md`](METHODOLOGY.md). Enfoque híbrido con **una sola fuente de verdad**:

- **Features:** Elo interno, FIFA ranking (opcional), forma reciente, GF/GC, diferencia de goles,
  tipo/importancia, sede.
- **Modelo de goles:** Poisson / Dixon-Coles (corrige dependencia en marcadores bajos) → matriz de
  marcadores → W/D/L por suma de zonas.
- **Calibración:** capa explícita (Platt por defecto con poca data; isotonic solo si hay volumen y
  mejora out-of-time), validada temporalmente.
- **Challenger ML:** logistic/ordinal regularizada + **un** GBM (LightGBM o XGBoost, no ambos),
  admitido solo si bate las marginales de la matriz out-of-time. RF como baseline didáctico.
- **Incertidumbre:** propagación paramétrica al Monte Carlo (roadmap); shrinkage para equipos con
  poca data.
- **Simulación:** Monte Carlo (N ≥ 50k) con bracket oficial, resolución de knockout y desempates.

**Orden de modelado (clave):** baselines → matriz de marcadores → calibración → match-level
backtesting (+ go/no-go) → challenger ML → simulación. La calibración va **antes** del simulador
que la consume.

---

## 7. Estrategia de backtesting (resumen)

Detalle en [`BACKTESTING_STRATEGY.md`](BACKTESTING_STRATEGY.md).

- **Match-level (criterio principal):** walk-forward expanding-window con corte por fecha; métricas
  primarias log loss + Brier + RPS multiclase + calibración; accuracy degradada a descriptiva;
  baselines obligatorios; tests pareados (Diebold-Mariano/bootstrap) para comparar modelos;
  skill score vs Elo-only.
- **Go/no-go:** superar a Elo-only en Brier/Log Loss con calibración aceptable.
- **Tournament-level (sanity check):** simular Mundiales 2010/2014/2018/2022 con `cutoff_date`;
  RPS sobre distribución de fase; nunca criterio de selección; reconocer N=4 y validez externa nula
  para el formato 2026 (32→48).
- **Anti-leakage:** corte estricto, Elo interno, series *as-of*, tests automáticos.

---

## 8. Simulación del Mundial 2026

- **Formato:** 48 equipos, 12 grupos de 4; clasifican 2 primeros + 8 mejores terceros → Round of 32
  → eliminatorias hasta la final.
- **Datos confirmados (al 2026-06-11):** torneo 11-jun → 19-jul-2026; 16 sedes en 3 países; 104
  partidos; inaugural en el Estadio Azteca (México vs Sudáfrica); final en el MetLife Stadium. Los 48
  equipos y los 12 grupos (A–L) están confirmados (sorteo dic-2025 + repechajes marzo-2026). Se
  cargan como `seed` en `groups`/`scheduled_matches`, no como placeholder.
- **Grupos:** desempates según reglamento oficial verificado (addendum §7), con tests.
- **Round of 32:** emparejamiento por `third_place_bracket_mapping` oficial (addendum §6), con test
  de validez de bracket.
- **Knockout:** sin empates; 90' → extra time (tasa reducida) → penalties (~50/50 + ajuste leve)
  (addendum §5), con test.
- **Monte Carlo:** N ≥ 50k; persistir solo agregados (`simulation_results`); reportar error de
  Monte Carlo por probabilidad de fase; seed persistida.
- **Placeholders:** si un detalle de bracket/fixture/clasificados/reglas no está confirmado, se usa
  placeholder explícito. **No** se inventan datos.
- **Uso durante el torneo (live forecasting):** a medida que se definen los cruces reales, el motor
  re-simula las rondas restantes y publica probabilidades **antes** de cada ronda, que luego se
  puntúan con los resultados reales (ver `BACKTESTING_STRATEGY.md` §live scoring).

---

## 9. Backend (diseño, no implementación aún)

FastAPI, endpoints previstos (capa fina): `GET /health`, `GET /teams`, `GET /teams/{team_id}`,
`POST /predict-match`, `GET /scoreline-matrix`, `POST /run-tournament-simulation`,
`GET /tournament-probabilities`, `GET /backtest-results`, `GET /model-runs/{run_id}`.

**Cómputo pesado:** las simulaciones Monte Carlo se **precomputan** vía scripts y se persisten; la
API solo lee agregados. La API no ejecuta cómputo pesado síncrono dentro de un request.

---

## 10. Frontend (diseño, OPCIONAL y no-bloqueante)

React + Vite. **Solo** se construye tras superar el go/no-go. En V1, la visualización puede ser un
notebook de evaluación o un dashboard ligero. Pantallas previstas (cuando aplique): dashboard,
predicción por partido, matriz de marcador, simulador, probabilidades por selección/fase, bracket,
comparador, resultados de backtesting, explicación del modelo. Toda probabilidad se comunica con su
banda de incertidumbre y contexto de calibración (comunicación honesta).

---

## 11. Fases (resumen)

Detalle por fase en [`PHASES.md`](PHASES.md). Secuencia: documentación → datos/snapshots →
identidad/mapping → cutoff logic → baselines → matriz de marcadores → match-level backtesting
(+ go/no-go) → tournament-level sanity check → simulador 2026 → API → frontend (opcional) → polish.

---

## 12. Riesgos principales

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Leakage por Elo/ranking recalculado | Alto | Elo interno; series *as-of*; `test_no_future_leakage` |
| Doble fuente de verdad W/D/L | Alto | Matriz única; `test_wdl_single_source` |
| Selección de modelo sobre N=4 | Alto | Selección por match-level; tournament-level solo sanity check |
| Reproducibilidad aparente | Alto | Metadata `NOT NULL`; lockfile; snapshots+hash |
| Explosión de volumen de simulación | Alto | Solo agregados en BD; muestra opcional |
| Identidad de equipos mal atribuida | Alto | `team_identity_periods` + aliases + política de sucesión |
| Bracket R32 inválido | Alto | `third_place_bracket_mapping` + `test_valid_bracket` |
| Sobreconfianza en knockout | Medio | Submodelo prórroga/penales validado |
| Validez externa nula para 2026 (32→48) | Medio | Separar validación del motor de propagación; comunicarlo |
| Sobre-ingeniería (web/infra) antes de validar | Medio | Go/no-go bloqueante; web no-bloqueante |
| Alcance vs calendario (torneo en curso) | Medio | Núcleo mínimo entregable + live scoring |

---

## 13. Supuestos y pendientes de verificación

- Reglamento oficial 2026 (**desempates de grupos** y **mapeo de terceros a R32**): **verificado**
  contra `FWC2026_regulations_EN.pdf` (Article 13 + Annex C). Pendiente de **implementación**:
  transcribir las 495 filas del Annex C a `third_place_bracket_mapping` (el detalle celda-a-celda no
  se extrajo del PDF; la estructura está confirmada).
- Fuentes verificadas (2026-06-11): Kaggle martj42 (CC0), OpenFootball/worldcup.json (CC0),
  StatsBomb (User Agreement, no comercial). Parciales: eloratings.net (sin licencia confirmada → Elo
  interno) y FIFA ranking (ToS restrictivos). Detalle en [`DATA_SOURCES.md`](DATA_SOURCES.md).
- Pesos por tipo de partido, ventanas temporales y método de calibración: **no** se fijan a priori;
  se validan por backtesting.
