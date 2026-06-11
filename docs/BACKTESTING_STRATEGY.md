# BACKTESTING_STRATEGY — World Cup 2026 Forecast Engine

> Documento de estrategia de backtesting (en español). Identificadores técnicos en inglés.
> Reglas vinculantes en [`METHODOLOGY_ADDENDUM.md`](METHODOLOGY_ADDENDUM.md).
> **Última actualización:** 2026-06-11.

El backtesting es **fase central**, no un extra. Tiene dos niveles con **roles distintos**:
match-level es el **criterio de selección**; tournament-level es **solo sanity check**.

---

## 1. Principio rector: el N manda

- **Match-level:** miles de partidos internacionales → potencia estadística suficiente para
  seleccionar modelos, ventanas, pesos y features.
- **Tournament-level:** solo 4 Mundiales útiles (2010, 2014, 2018, 2022) → **N=4**, sin potencia
  para distinguir estrategias. Elegir "la combinación que mejor backtesteó" sobre 4 torneos es
  **seleccionar ruido**.

**Regla (addendum §3):** la selección real de modelo/ventana/peso/features se hace con
**match-level**. El tournament-level **nunca** es criterio de selección. **Prohibido** elegir un
modelo por haber "acertado" el campeón de un Mundial pasado.

---

## 2. Match-level backtesting (criterio principal)

### 2.1 Protocolo temporal

- **Walk-forward expanding-window** con corte por fecha. **Prohibido** k-fold aleatorio sobre datos
  temporales (filtra el futuro aunque no haya features explícitamente futuras).
- Para cada partido, el modelo usa solo información disponible **antes** de ese partido (o antes del
  torneo, según el tipo de evaluación).
- Embargo entre fin de train y el test cuando aplique.
- Selección de hiperparámetros con **CV temporal anidada** (un bloque de validación anterior al de
  test), nunca tocando el bloque de test.

### 2.2 Métricas

- **Primarias:** log loss, Brier score, RPS multiclase, calibración (ECE + reliability diagram con
  bandas bootstrap), MAE/RMSE de goles esperados.
- **Descriptiva (no de selección):** accuracy W/D/L. Se degrada porque en un problema 3-clase con
  empate ~22-28% puede premiar al peor modelo probabilístico.
- **Relativa:** **skill score** = `1 - loss_model / loss_baseline` frente a Elo-only.

### 2.3 Baselines obligatorios (addendum §15)

- `elo_only_baseline`
- `fifa_ranking_baseline` (si hay datos disponibles como serie *as-of*)
- `simple_poisson_baseline`
- `naive_favorite_baseline` (si aplica)

### 2.4 Comparación entre modelos (significancia)

Decir "A es mejor que B" requiere un **test pareado** sobre las pérdidas por partido
(bootstrap pareado o Diebold-Mariano), reportando p-valor o IC de la diferencia, no solo el punto.

### 2.5 Control de sobreajuste al backtest

- Acotar el espacio de búsqueda (ventanas × pesos × modelos × cutoffs) **a priori**. Ventanas
  temporales candidatas a evaluar (no se asume cuál es mejor; del prompt maestro): `window_2000`,
  `window_2010`, `window_2014`, `window_last_cycle`, `window_weighted_modern`.
- Exigir que la configuración ganadora lo sea de forma **estable a través de todos los cutoffs**,
  no solo en agregado.
- Reservar el conjunto más reciente como **hold-out final intocado** durante la selección.
- Aplicar **corrección por comparaciones múltiples**.
- Reportar la **dispersión** de las métricas, no solo la media.

---

## 3. Go/no-go cuantitativo (addendum §4)

Criterio de aceptación **duro** de esta fase:

```text
The V1 forecasting engine must outperform an Elo-only baseline in out-of-time match-level
Brier Score or Log Loss, while maintaining acceptable calibration, before investing in a
full frontend or player-level V2.
```

```text
El motor V1 debe superar a un baseline Elo-only en Brier Score o Log Loss con calibración
aceptable antes de invertir en frontend completo o V2.
```

Si no se supera: documentar el resultado en `backtest_metrics`, **no** avanzar a frontend/V2, y
mejorar la metodología (features, calibración, modelo de goles) antes de continuar.

---

## 4. Tournament-level backtesting (sanity check)

### 4.1 Procedimiento

Para cada Mundial histórico (2010/2014/2018/2022):

1. Definir `cutoff_date` antes del inicio del torneo.
2. Entrenar/ajustar **solo** con datos pre-cutoff (Elo interno, rankings *as-of*, features *as-of*).
3. Simular el torneo completo muchas veces (N ≥ 50k).
4. Comparar probabilidades de fase y de campeón contra los resultados reales.
5. Analizar si el campeón real estaba entre candidatos razonables (no juzgar solo por acertarlo).

### 4.2 Métrica primaria

**RPS** (Ranked Probability Score) sobre la distribución **ordinal** de fase por equipo, promediado
sobre equipos y torneos. Para eventos binarios concretos (p. ej. P(campeón) del campeón real) se usa
log loss/Brier con su baseline.

### 4.3 Correlación intra-torneo

Los partidos de un mismo torneo **no** son independientes. Para todo IC agregado de nivel torneo se
usa **block bootstrap por torneo** (remuestrear torneos completos) y errores estándar **clusterizados
por torneo**. El número efectivo de observaciones independientes a nivel torneo es **cercano a 4**,
no a ~250.

### 4.4 Validez externa para 2026

El formato cambia 32→48 equipos: **ningún** torneo histórico valida la estructura de bracket de
2026. Por tanto:

- El tournament-level valida el **motor de propagación** (avance de bracket, agregación de
  probabilidades), **no** la estructura específica de 2026.
- Validar el módulo de avance con **golden tests sintéticos** de propiedades conocidas (ver §6).
- Comunicar sin ambigüedad que las probabilidades de fase 2026 **no** tienen análogo histórico
  directo.

### 4.5 Qué es y qué no es evaluable

- Evaluable con datos disponibles: P(alcanzar octavos), P(top-2 de grupo) — decenas de eventos por
  torneo.
- Prácticamente **no** calibrable con N=4: P(campeón) (evento de cola). Se declara explícitamente.

---

## 5. Anti-leakage en backtesting (addendum §1)

- Corte estricto por `cutoff_date`; Elo recalculado internamente; rankings *as-of*.
- `test_no_future_leakage` corre como parte del backtesting.
- Cada `backtest_run` guarda `cutoff_date`, `data_hash`, `git_sha`, `random_seed`, `python_version`,
  `package_lock` (`NOT NULL`).
- El backtesting **pinea snapshots** inmutables de fuentes, no lee fuentes vivas.

---

## 6. Golden tests de lógica deportiva (obligatorios)

Más valiosos que la cobertura de líneas:

- `test_valid_bracket`: ninguna simulación genera cruces inválidos en R32 (addendum §6).
- `test_no_draws_in_knockout`: ninguna ronda knockout termina en empate (addendum §5).
- `test_group_tiebreakers`: casos construidos de empate en grupos se resuelven según reglamento
  (addendum §7).
- Coherencia de probabilidades: por equipo, `P(R32) >= P(R16) >= P(QF) >= P(SF) >= P(Final) >=
  P(Champion)` (monotonía); Σ `champion_probability` sobre los 48 equipos ≈ 1.
- `test_unmapped_tournaments`: no hay torneos sin mapear (addendum §11).
- `test_wdl_single_source`: W/D/L coherente entre componentes (addendum §2).

---

## 7. Live scoring durante el torneo 2026

Validación **real** y anti-humo del motor: publicar probabilidades **antes** y puntuarlas **después**.

- **Pre-ronda:** antes de cada ronda (fase de grupos, R32, R16, QF, SF, Final), congelar las
  probabilidades publicadas con su `model_run`/`tournament_simulation` y `cutoff_date` = fecha de
  publicación.
- **Post-ronda:** con los resultados reales, calcular log loss / Brier / RPS de lo publicado y
  compararlo con los baselines (Elo-only, etc.).
- **Re-simulación:** a medida que se conocen los cruces reales, re-simular las rondas restantes
  (manteniendo el corte estricto: solo información disponible al momento de publicar).
- Registrar todo en `backtest_runs`/`backtest_metrics` con `backtest_level = 'live'` para
  trazabilidad.

> Esta es la única prueba definitiva de calidad del motor para 2026, dado que el backtest histórico
> no cubre el formato de 48 equipos.

---

## 8. Resumen de roles

| Nivel | Rol | Criterio de selección | Métrica primaria |
|-------|-----|------------------------|------------------|
| match-level | Selección de modelo | **Sí** | log loss, Brier, RPS, calibración |
| tournament-level | Sanity check histórico | No | RPS de distribución de fase |
| live scoring 2026 | Validación real en curso | No (evaluación) | log loss, Brier, RPS vs baselines |
