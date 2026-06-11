# Addendum metodológico obligatorio (v1)

> **Estado:** Vinculante. Este documento es un *addendum obligatorio* al prompt maestro original
> (`World Cup 2026 Forecast Engine`). **No reemplaza** al prompt maestro: lo corrige y lo precisa.
> En caso de conflicto entre el prompt maestro y este addendum, **prevalece este addendum**.
>
> **Idioma:** redactado en español (documento de guía). Todos los identificadores técnicos
> (tablas, columnas, funciones, endpoints, ramas, categorías) están en inglés y son **canónicos**:
> deben usarse exactamente igual en todo el repositorio.
>
> **Fecha de incorporación:** 2026-06-11.

Este addendum recoge 16 observaciones metodológicas críticas detectadas en una revisión
multi-experto del prompt maestro. Cada punto define: el riesgo, la regla obligatoria, los
identificadores canónicos asociados y los tests que deben existir. Los documentos
`PROJECT_BLUEPRINT.md`, `METHODOLOGY.md`, `BACKTESTING_STRATEGY.md`, `DATA_SOURCES.md` y
`PHASES.md` desarrollan estos puntos; este archivo es la **fuente de verdad** de las reglas.

---

## 1. Data leakage por Elo/FIFA/rankings recalculados

**Riesgo (#1 del proyecto):** un Elo o ranking descargado hoy puede incorporar resultados
posteriores al `cutoff_date`. Usarlo en un backtest histórico **filtra el futuro** e invalida
todo el backtesting.

**Reglas obligatorias:**

- En backtesting histórico, **ningún** feature, rating o ranking puede usar información posterior
  al `cutoff_date` del experimento.
- El Elo se **recalcula internamente** desde resultados crudos (`matches`) con corte estricto por
  fecha. No se confía en un Elo externo "pre-torneo" descargado hoy.
- Los rankings externos se modelan como **series temporales bitemporales** con las columnas:
  `publication_date`, `effective_from`, `effective_to`, `source_name`, `source_version`,
  `data_hash`.
- Toda lectura de feature usa el último registro con `effective_from <= cutoff_date`
  (lookup *as-of*), nunca el valor "actual".

**Tests obligatorios:** `test_no_future_leakage` — falla si cualquier feature, ranking o rating
usado para un partido tiene una fecha (`publication_date` / `match_date` de origen) posterior al
`cutoff_date` de la corrida.

**Documentado en:** `METHODOLOGY.md`, `BACKTESTING_STRATEGY.md`, `DATA_SOURCES.md`.

---

## 2. Una sola fuente oficial para W/D/L

**Riesgo:** tener tres probabilidades distintas para el mismo partido (matriz, clasificador ML,
simulador) destruye la coherencia y la credibilidad.

**Fuente oficial única en V1:**

1. Modelo de goles tipo **Poisson / Dixon-Coles** (o variante equivalente).
2. **Matriz de probabilidad de marcadores** (`scoreline_probabilities`).
3. W/D/L **derivado** sumando zonas de la matriz.

**Reglas de derivación (canónicas):**

- `p_team_a_win` = Σ celdas donde `goals_a > goals_b`
- `p_draw` = Σ celdas donde `goals_a = goals_b`
- `p_team_b_win` = Σ celdas donde `goals_b > goals_a`

**Modelo ML:** existe solo como `challenger_model`, **nunca** como segunda fuente oficial. Solo
puede reemplazar o re-pesar la matriz base si **gana en backtesting out-of-time** (Log Loss /
Brier Score) y mantiene calibración aceptable; en ese caso re-normaliza la matriz, no corre en
paralelo.

**Test obligatorio:** `test_wdl_single_source` — verifica que las probabilidades W/D/L usadas por
frontend, API, backtesting y Monte Carlo provienen de la **misma** matriz (dentro de tolerancia
numérica).

---

## 3. Selección de modelo a nivel partido, no por campeón de torneo

**Riesgo:** elegir el "mejor" modelo/ventana usando 4-5 Mundiales es seleccionar ruido (N
minúsculo).

**Reglas:**

- `match-level backtesting` = **criterio principal** de selección de modelo, pesos, ventanas y
  features (miles de partidos).
- `tournament-level backtesting` = **sanity check** secundario, nunca criterio de selección.
- **Prohibido** elegir un modelo por haber "acertado" el campeón de un Mundial pasado.

**Documentado en:** `BACKTESTING_STRATEGY.md`.

---

## 4. Go/no-go cuantitativo (regla bloqueante)

Antes de invertir en frontend completo o V2:

```text
The V1 forecasting engine must outperform an Elo-only baseline in out-of-time match-level
Brier Score or Log Loss, while maintaining acceptable calibration, before investing in a
full frontend or player-level V2.
```

```text
El motor V1 debe superar a un baseline Elo-only en Brier Score o Log Loss con calibración
aceptable antes de invertir en frontend completo o V2.
```

Si no supera el baseline, se documenta el resultado y se mejora la metodología **antes** de
continuar. Es un criterio de aceptación **duro** de la fase de match-level backtesting.

---

## 5. Empates en eliminatorias

**Regla:** el simulador no puede dejar empates en knockout. Cada partido de eliminatoria debe
producir un ganador resolviendo: `90 minutes -> extra time -> penalties`.

**Reglas de modelado (V1, submodelo simple pero existente y documentado):**

- En fase de grupos, el empate es resultado válido.
- En eliminatorias, prórroga modelada con **tasa de gol reducida**.
- Penales modelados como **~50/50**, con ajuste leve por fuerza relativa solo si se justifica.

**Test obligatorio:** `test_no_draws_in_knockout` — falla si alguna ronda knockout termina en
empate.

---

## 6. Bracket oficial de Round of 32

**Formato 2026:** 48 equipos, 12 grupos de 4; clasifican los **dos primeros** de cada grupo y los
**ocho mejores terceros**.

**Reglas:**

- **Prohibido** emparejar a los terceros "a ojo" o aleatoriamente.
- **Verificado:** clasifican 8 de 12 terceros ⇒ **495 combinaciones** posibles (C(12,8)), publicadas
  por FIFA en el **Annex C** del reglamento (`FWC2026_regulations_EN.pdf`). El cuadro se **bloquea
  automáticamente** al cerrar la fase de grupos (no hay segundo sorteo). Los 16 partidos de R32
  (Match 73–88) tienen slots de 1.º/2.º **fijos**; solo flota qué grupo aporta cada tercero (cada
  slot de tercero admite 5 grupos concretos). Regla: ningún tercero repite rival de su propio grupo.
- El bracket de R32 es un **artefacto de datos de primer nivel**, versionado:
  `third_place_bracket_mapping` (las 495 combinaciones → slots de R32).
- **Pendiente de implementación:** transcribir las 495 filas del Annex C desde el PDF oficial (el
  detalle celda-a-celda no se extrajo del PDF; estructura confirmada vía fuentes secundarias).

**Test obligatorio:** `test_valid_bracket` — rechaza cruces imposibles o inválidos en R32.

---

## 7. Desempates de grupos

**Regla:** no inventar reglas. Cascada **verificada** contra el documento oficial
*Regulations for the FIFA World Cup 26*, **Article 13** (ed. mayo 2026):

Criterio base: mayor número de **puntos** (Art. 12.4). Si hay empate a puntos:

- **Step 1 — head-to-head** (solo partidos entre los empatados): a) puntos; b) diferencia de goles;
  c) goles a favor.
- **Step 2:** re-aplicar Step 1 a los que sigan empatados; si no decide, criterios **globales**:
  d) diferencia de goles global; e) goles a favor global; f) **team conduct score** (disciplina:
  amarilla −1, roja indirecta −3, roja directa −4, amarilla+roja directa −5; jugadores y oficiales;
  más puntos = mejor).
- **Step 3:** g) **ranking FIFA** más reciente; h) ediciones previas del ranking FIFA hasta decidir.

**No** hay sorteo. **Novedad 2026:** el head-to-head se aplica **antes** que la diferencia de goles
global (cambio respecto a 2018/2022). Para rankear a los **8 mejores terceros** se usan solo
criterios globales (puntos → DG global → goles global → conduct score → ranking FIFA), no
head-to-head. Fuente: `FWC2026_regulations_EN.pdf` (FIFA Digital Hub).

La cascada se almacena como **artefacto versionado** (`tournament_format.group_tiebreaker_rules`
con `mapping_version`), análogo a `third_place_bracket_mapping`; el test corre sobre la cascada
parametrizada, no sobre un orden hardcodeado.

**Test obligatorio:** `test_group_tiebreakers` — valida casos construidos de empate en grupos.

---

## 8. Reproducibilidad real (mecanizada)

Cada corrida importante (`model_runs`, `tournament_simulations`, `backtest_runs`) guarda metadata
**`NOT NULL`** que permita reconstruirla:

```text
simulation_id / run_id
model_version
model_name
git_sha
data_hash
cutoff_date
random_seed
number_of_simulations
created_at
python_version
package_lock
```

**Requisitos:** versión de Python fija; lockfile/dependencias versionadas; seed reproducible;
hash/checksum de datasets; snapshots inmutables de fuentes; no sobrescribir resultados sin
versionado; tests reproducibles.

---

## 9. No guardar millones de simulaciones crudas en PostgreSQL

**Regla:** no persistir todos los partidos de todas las simulaciones (cientos de millones de filas
colapsarían PostgreSQL local).

**Persistir principalmente:**

- metadata de la corrida (`tournament_simulations`);
- probabilidades agregadas por selección/fase (`simulation_results`): champion probabilities,
  group qualification probabilities, stage probabilities;
- una muestra pequeña de simulaciones completas solo para debugging (`simulation_sample`,
  opcional, con seed fijo).

Documentado en la arquitectura de datos (`PROJECT_BLUEPRINT.md`).

---

## 10. Identidad temporal de equipos

**Regla:** manejar cambios históricos de nombre/identidad sin colapsar ni duplicar equipos sin
decisión explícita.

**Ejemplos:** Yugoslavia / Serbia · USSR / Russia · Czechoslovakia / Czech Republic ·
Czech Republic / Czechia · Macedonia / North Macedonia.

**Tablas canónicas:** `teams`, `team_aliases`, `team_identity_periods`.

La limpieza/normalización de nombres está **versionada y testeada**. La política de sucesión
(qué identidad hereda a cuál) se documenta y se trata como decisión backtesteable.

---

## 11. Tournament mapping versionado

**Riesgo:** los datasets traen `tournament` como texto libre (cientos de valores).

**Tabla canónica:** `tournament_mapping`, con categorías limpias:

```text
world_cup
continental_cup
qualifier
nations_league
friendly
other
```

Cada torneo se mapea a: `tournament_category`, `match_importance_weight`, `confederation_scope`,
`is_official`, `source`, `mapping_version`.

**Test obligatorio:** `test_unmapped_tournaments` — detecta y falla ante torneos no mapeados.

---

## 12. Shrinkage para equipos con poca información

**Regla (roadmap metodológico):** en 2026 habrá equipos con poca historia comparable. No estimar
su fuerza solo con pocos datos recientes. Estrategia de `shrinkage`/regularización hacia:

- promedio global;
- promedio por confederación;
- ranking/Elo esperado;
- fuerza histórica ajustada.

No es obligatorio implementarlo completo en V1, pero **debe estar en el roadmap** y propagarse la
incertidumbre al Monte Carlo cuando se implemente.

---

## 13. Sede, altitud, calor y anfitriones

**Regla:** un solo `is_neutral` no captura las condiciones de un Mundial en tres países. Features
**candidatas** (documentadas, no obligatorias en V1):

```text
venue_country
venue_city
is_host_team
is_home_region
venue_altitude
temperature_bucket
travel_distance_proxy
```

No sobrecomplicar V1, pero dejarlo contemplado y reservar las columnas en el diseño.

---

## 14. StatsBomb y licencias

**Regla:** StatsBomb Open Data **no** es dato completamente libre sin condiciones. Para V2/V3:

- revisar el *user agreement* vigente;
- respetar la atribución (incluido logo si corresponde);
- **no** subir crudos al repo si no corresponde;
- documentar instrucciones de descarga (script), no el dato crudo;
- **no usar StatsBomb en V1**.

---

## 15. Odds / apuestas

**Regla:** **no** usar odds de casas de apuestas en V1. Mantener analítica deportiva limpia.
Pueden mencionarse como **benchmark externo futuro**, no implementarse ahora.

**Benchmarks permitidos en V1:**

- `elo_only_baseline`;
- `fifa_ranking_baseline`;
- `simple_poisson_baseline`;
- `naive_favorite_baseline` (si aplica).

---

## 16. Actualización de fases

La secuencia de fases prioriza datos y validación del motor **antes** que web. Orden de prioridad:

1. documentación y arquitectura;
2. datos y snapshots;
3. limpieza e identidad de equipos;
4. cutoff logic;
5. baselines;
6. matriz de probabilidad de marcadores;
7. match-level backtesting (+ go/no-go);
8. tournament-level sanity check;
9. simulador 2026;
10. recién después API/frontend.

**No** construir una web grande antes de validar que el motor supera un baseline razonable. El
detalle por fase está en `PHASES.md`.

---

## Trazabilidad: punto del addendum → documento/artefacto

> El "documento principal" indica dónde vive el desarrollo narrativo; el **esquema e identificadores
> canónicos** de tablas/columnas viven siempre en `PROJECT_BLUEPRINT.md` §5.

| #  | Tema                              | Documento principal            | Artefacto/test clave                        |
|----|-----------------------------------|--------------------------------|---------------------------------------------|
| 1  | Leakage Elo/ranking               | `METHODOLOGY.md`               | `test_no_future_leakage`, Elo interno       |
| 2  | Única fuente W/D/L                 | `METHODOLOGY.md`               | `test_wdl_single_source`                    |
| 3  | Selección a nivel partido         | `BACKTESTING_STRATEGY.md`      | match-level como criterio principal         |
| 4  | Go/no-go                          | `BACKTESTING_STRATEGY.md`      | gate Brier/Log Loss vs Elo-only             |
| 5  | Empates knockout                  | `METHODOLOGY.md`               | `test_no_draws_in_knockout`                 |
| 6  | Bracket R32                       | `PROJECT_BLUEPRINT.md`         | `third_place_bracket_mapping`, `test_valid_bracket` |
| 7  | Desempates de grupos              | `PROJECT_BLUEPRINT.md` §5.8 / `BACKTESTING_STRATEGY.md` §6 | `group_tiebreaker_rules`, `test_group_tiebreakers` |
| 8  | Reproducibilidad                  | `METHODOLOGY.md`               | metadata `NOT NULL` en runs                 |
| 9  | No simulaciones crudas en BD      | `PROJECT_BLUEPRINT.md`         | `simulation_results` (agregados)            |
| 10 | Identidad de equipos              | `PROJECT_BLUEPRINT.md`         | `team_identity_periods`, `team_aliases`     |
| 11 | Tournament mapping                | `PROJECT_BLUEPRINT.md` §5.1 (esquema) / `DATA_SOURCES.md` (fuente) | `tournament_mapping`, `test_unmapped_tournaments` |
| 12 | Shrinkage                         | `METHODOLOGY.md`               | roadmap de regularización                   |
| 13 | Sede/altitud/calor                | `METHODOLOGY.md`               | features candidatas de venue                |
| 14 | StatsBomb/licencias               | `DATA_SOURCES.md`              | política de no-redistribución               |
| 15 | Odds / benchmarks                 | `BACKTESTING_STRATEGY.md` §2.3 / `DATA_SOURCES.md` | benchmarks permitidos V1 (4 baselines)      |
| 16 | Fases                             | `PHASES.md`                    | secuencia reordenada                        |
