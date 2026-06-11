# METHODOLOGY — World Cup 2026 Forecast Engine

> Documento de metodología (en español). Identificadores técnicos en inglés.
> Reglas vinculantes en [`METHODOLOGY_ADDENDUM.md`](METHODOLOGY_ADDENDUM.md).
> Backtesting en [`BACKTESTING_STRATEGY.md`](BACKTESTING_STRATEGY.md).
> **Última actualización:** 2026-06-11.

Este documento define **cómo** se modela y **qué reglas metodológicas** son obligatorias. Está
escrito para evitar los dos fallos que arruinan los pronósticos deportivos: **data leakage** e
**incoherencia entre fuentes de probabilidad**.

---

## 1. Principios

1. **Una sola fuente de verdad probabilística por partido** (addendum §2).
2. **Cero información posterior al `cutoff_date`** (addendum §1).
3. **Baselines primero**; nada complejo sin batir lo simple (addendum §3, §4).
4. **Calibración explícita y validada temporalmente** antes de consumir probabilidades aguas abajo.
5. **Reproducibilidad mecanizada**, no declarativa (addendum §8).
6. **Comunicación honesta de incertidumbre**: toda probabilidad lleva su banda y su contexto de
   calibración.

---

## 2. Prevención de data leakage (riesgo #1)

### 2.1 Regla de corte

Para cualquier experimento histórico se fija un `cutoff_date`. **Ningún** feature, rating o ranking
puede usar información con fecha posterior al `cutoff_date`.

### 2.2 Elo recalculado internamente

El Elo de selecciones se **recalcula desde `matches`** con corte estricto por fecha. No se usa un
Elo externo "pre-torneo" descargado hoy, porque esos ficheros suelen estar **recalculados
retroactivamente** e incorporan resultados posteriores al corte.

- `elo_ratings` guarda Elo **pre-match** y **post-match** por partido (auditable).
- La fórmula de actualización (K-factor, ajuste por margen de victoria, ventaja de localía, factor
  por tipo de partido) se documenta y se trata como hiperparámetro a validar (no se fija a priori).
- El Elo inicial de equipos con poca historia se inicializa con un prior (ver §6 shrinkage).

### 2.3 Rankings externos como series bitemporales

`rankings` (p. ej. FIFA) se modela como serie temporal con `publication_date`, `effective_from`,
`effective_to`, `source_name`, `source_version`, `data_hash`. La lectura de feature usa siempre el
**último registro con `effective_from <= cutoff_date`** (lookup *as-of*). El FIFA ranking se trata
como **feature opcional y baseline**, no como columna garantizada (solo existe desde 1992 y cambió
de metodología en 2018; serie no homogénea — ver `DATA_SOURCES.md`).

### 2.4 Feature store point-in-time

`match_features` se construye *as-of cutoff* y versiona con `feature_pipeline_version`,
`cutoff_date`, `code_git_sha`.

### 2.5 Tests de leakage (obligatorios)

- `test_no_future_leakage`: falla si cualquier feature/ranking/rating usado para un partido tiene
  fecha posterior al `cutoff_date`.
- Comprobación de que el Elo usado para un partido es el **pre-match** (no el post-match).

---

## 3. Modelo base: una sola fuente de verdad para W/D/L (addendum §2)

### 3.1 Modelo de goles → matriz de marcadores

Modelo de goles tipo **Poisson / Dixon-Coles**:

- Se estiman intensidades de gol esperadas para cada equipo (`expected_goals_a`, `expected_goals_b`)
  a partir de las features (fuerza ofensiva/defensiva, localía, etc.).
- Dixon-Coles añade el parámetro de dependencia (tau) para corregir la sub-estimación de marcadores
  bajos (0-0, 1-0, 0-1, 1-1), frecuentes en selecciones.
- Se construye la **matriz de probabilidad de marcadores** (`scoreline_probabilities`), filas =
  goles del equipo A, columnas = goles del equipo B, truncada en un máximo de goles razonable y
  re-normalizada.

### 3.2 Derivación de W/D/L (canónica)

```text
p_team_a_win = sum( cells where goals_a > goals_b )
p_draw       = sum( cells where goals_a = goals_b )
p_team_b_win = sum( cells where goals_b > goals_a )
```

**Estas tres probabilidades son la fuente oficial.** Frontend, API, backtesting y Monte Carlo
**deben** consumir exactamente estas, derivadas de la misma matriz.

### 3.3 Test de consistencia (obligatorio)

`test_wdl_single_source`: verifica (dentro de tolerancia) que las marginales W/D/L expuestas por
todos los componentes coinciden con las derivadas de la matriz.

---

## 4. Challenger ML (no es segunda fuente oficial)

Un modelo ML existe solo como `challenger_model`:

- Candidatos: **logistic/ordinal regularizada** (W/D/L es **ordinal**: derrota < empate < victoria)
  y **un** GBM (LightGBM **o** XGBoost, no ambos). RF queda como baseline didáctico, no candidato
  de producción. **Sin** ensembling en V1.
- Admisión: solo si **bate** las marginales de la matriz base en log loss/Brier **out-of-time** de
  forma **estable a través de todos los cutoffs**, no en un solo split.
- Si se admite, **re-pesa y re-normaliza** la matriz para respetar las marginales mejoradas; nunca
  corre en paralelo produciendo cifras distintas.
- SHAP/feature importance: con features colineales (Elo, FIFA, forma, diferencia de goles) la
  importancia es **inestable y no causal**; se reporta importancia por permutación con CV temporal,
  agrupando features correlacionados, y se comunica como rango, no ranking puntual.

---

## 5. Calibración (antes del simulador)

- Método por defecto: **Platt/sigmoide** (más robusto con poca data). **Isotonic** solo si hay
  volumen suficiente y mejora la reliability out-of-time.
- W/D/L es multiclase: calibración one-vs-rest + renormalización (o multinomial), de forma
  coherente.
- **Validación temporal:** la calibración se ajusta en un bloque temporal separado del de
  entrenamiento y del de test final; se mide con reliability diagram + ECE con bandas (bootstrap).
- **Orden:** la capa de calibración se define y valida **antes** de construir el Monte Carlo que la
  consume (probabilidades no calibradas → P(campeón) sesgada).

---

## 6. Incertidumbre y shrinkage (addendum §12)

- **Shrinkage / partial pooling** para equipos con poca historia (debutantes del formato de 48):
  regularización de la fuerza hacia un prior (promedio global, promedio por confederación,
  ranking/Elo esperado, fuerza histórica ajustada). Roadmap metodológico; no obligatorio completo
  en V1, pero debe estar previsto.
- **Propagación de incertidumbre paramétrica:** el Monte Carlo debe (roadmap) muestrear los
  parámetros del modelo (bootstrap de coeficientes o posterior) en un bucle externo y simular
  partidos en el interno, para no producir intervalos de P(campeón) artificialmente estrechos.

---

## 7. Resolución de knockout (addendum §5)

En eliminatorias el partido debe producir un ganador:

1. **90 minutes:** marcador del modelo base.
2. **Extra time:** si hay empate, se simulan 30' con **tasa de gol reducida** (proporción a
   calibrar).
3. **Penalties:** si persiste el empate, ganador con probabilidad **~50/50** y ajuste leve por
   fuerza relativa solo si se justifica empíricamente.

`test_no_draws_in_knockout`: falla si alguna ronda knockout termina en empate. Las tasas de prórroga
y penales se validan contra frecuencias históricas de Mundiales.

---

## 8. Features de contexto (addendum §13)

Sede modelada más allá de `is_neutral`. Features **candidatas** (reservadas en el diseño, no
obligatorias en V1): `venue_country`, `venue_city`, `is_host_team`, `is_home_region`,
`venue_altitude`, `temperature_bucket`, `travel_distance_proxy`. En 2026 (tres anfitriones,
altitud en México, calor de junio-julio) estos factores son relevantes; se documentan como
limitación mientras no se llenen.

Otros factores documentados como limitación: no-estacionariedad por cambio de DT/generación (decay
temporal global es una herramienta roma; inflar incertidumbre tras cambios de ciclo), bajas/lesiones
pre-partido (flag reservado en V1), comparabilidad inter-confederación (baja conectividad de
resultados), dead-rubbers (partidos sin incentivo).

---

## 9. Reproducibilidad mecanizada (addendum §8)

- **Entorno:** gestor único de dependencias con **lockfile** commiteado; `requires-python` fijo;
  `src/` instalable en modo editable (sin hacks de `sys.path`); grupos de dependencias
  dev/test/notebooks/api separados.
- **Semillas:** RNG centralizado en `src/utils`; semilla persistida por corrida; generadores
  independientes por worker (p. ej. `numpy` `SeedSequence.spawn`).
- **Metadata por corrida (`NOT NULL`):** `run_id` (`simulation_id` en `tournament_simulations`),
  `model_name`, `model_version`, `git_sha`, `data_hash`, `cutoff_date`, `random_seed`,
  `number_of_simulations` (sim), `python_version`, `package_lock`, `config_json`, `created_at`.
- **Datos:** snapshots inmutables en `data/raw` con manifest (fecha, URL, versión upstream, SHA-256);
  el backtesting **pinea** el snapshot, no la fuente viva.
- **Tests reproducibles:** una corrida con seed fijo reproduce resultados (igualdad dentro de
  tolerancia); documentar fuentes residuales de no-determinismo (paralelismo, BLAS).

---

## 10. Métricas (resumen; detalle en BACKTESTING_STRATEGY.md)

- **Primarias match-level:** log loss, Brier score, RPS multiclase, calibración (ECE/reliability).
- **Primaria tournament-level:** RPS sobre la distribución ordinal de fase.
- **Descriptivas (no de selección):** accuracy W/D/L, acierto de campeón.
- **Relativas:** skill score frente a Elo-only (y, a futuro, frente a mercado des-vigorizado como
  techo realista — no en V1).

---

## 11. Lo que NO se hace (en V1)

- No deep learning. No datos de clubes. No odds de apuestas. No StatsBomb.
- No fijar pesos/ventanas/calibración a priori (se validan).
- No usar el clasificador ML como fuente oficial paralela.
- No persistir simulaciones crudas masivas.
