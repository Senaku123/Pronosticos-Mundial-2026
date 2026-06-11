# DATA_SOURCES — World Cup 2026 Forecast Engine

> Documento de fuentes de datos (en español). Identificadores técnicos en inglés.
> Reglas vinculantes en [`METHODOLOGY_ADDENDUM.md`](METHODOLOGY_ADDENDUM.md).
> **Última actualización:** 2026-06-11.

> **Aviso de verificación.** Este documento describe fuentes **candidatas**. Varios datos
> (licencias, cobertura, disponibilidad de API, términos de uso) **deben verificarse manualmente**
> antes de integrarse, porque cambian con el tiempo. Los puntos marcados **`VERIFICAR MANUALMENTE`**
> son condición de aceptación de la Phase 2. **No se inventan fuentes ni datasets.**

---

## 1. Principios de datos (del addendum)

- **Anti-leakage (§1):** las fuentes de Elo/ranking que se descargan hoy pueden estar recalculadas
  retroactivamente. Por eso el Elo se **recalcula internamente** y los rankings se modelan como
  series **bitemporales** (`publication_date`, `effective_from`, `effective_to`, `source_name`,
  `source_version`, `data_hash`).
- **Tournament mapping (§11):** la columna `tournament` viene como texto libre; se normaliza con la
  tabla versionada `tournament_mapping`.
- **StatsBomb/licencias (§14):** no es dato libre sin condiciones; V2/V3 únicamente.
- **Sin odds en V1 (§15).**
- **Gobernanza:** snapshots inmutables con SHA-256 + fecha + URL en un manifest; `data/raw` fuera de
  git; licencia upstream vs licencia del paquete (prevalece la **más restrictiva**).

---

## 2. Ficha por fuente (plantilla)

Cada fuente se documenta con: `name`, `url`, `data_type`, `temporal_coverage`, `format`,
`requires_api_key`, `is_free`, `upstream_source`, `license`, `upstream_license`, `limitations`,
`use_in_project`, `legal_risk`, `verification_status`.

---

## 3. Fuentes candidatas (V1 — selecciones)

### 3.1 Kaggle — International football results (1872–present) · martj42

- **data_type:** resultados de partidos internacionales. `results.csv` tiene **9 columnas**
  (verificado): `date, home_team, away_team, home_score, away_score, tournament, city, country,
  neutral`. Archivos extra: `shootouts.csv`, `goalscorers.csv`, `former_names.csv`.
- **temporal_coverage:** 1872-11-30 → presente (repo vivo; ~48–49k partidos).
- **format:** CSV.
- **requires_api_key:** Kaggle exige cuenta + token (`kaggle.json`) para descarga programática.
  **Alternativa sin cuenta:** repo GitHub `martj42/international_results` (raw `results.csv`).
- **license:** **CC0 1.0 Universal** (dominio público), confirmada en el `LICENSE` del repo.
- **limitations:** `tournament` es **texto libre** → requiere `tournament_mapping` (addendum §11).
  **No** hay columna booleana de amistosos: `Friendly` es un **valor** de `tournament`. `neutral`
  **sí** es booleana (TRUE/FALSE).
- **use_in_project:** columna vertebral de V1 (base para `matches` y para recalcular Elo).
- **verification_status:** `VERIFIED (2026-06-11)`.

### 3.2 World Football Elo Ratings — eloratings.net

- **data_type:** Elo de selecciones.
- **format:** SPA en JavaScript, **sin** API ni export oficial (confirmado: home/about no renderizan
  vía fetch; `robots.txt` da 404). Acceso = **scraping** de terceros.
- **license:** **no se pudo verificar** ninguna licencia/ToS en el sitio → tratar como **copyright
  por defecto**, no como reutilizable libremente.
- **limitations / legal_risk:** ratings **secuenciales y backfilleados a 1872**; la tabla
  recalculada de hoy **no** equivale al Elo pre-torneo → **leakage** si se usa sin congelar fecha.
- **use_in_project:** **NO** como dependencia directa. Decisión canónica (addendum §1): **recalcular
  Elo internamente** desde `matches`. Datasets terceros (Kaggle saifalnimri, afonsofernandescruz)
  están etiquetados CC0 **por el uploader, no por el titular** → licencia jurídicamente incierta.
- **verification_status:** `VERIFIED — usar Elo interno`.

### 3.3 FIFA rankings

- **data_type:** ranking FIFA/Coca-Cola masculino (puntos/posición), con `rank_date`.
- **temporal_coverage:** desde **dic-1992** (mensual regular desde ago-1993). Metodologías por época,
  **no** recalculadas retroactivamente antes de jul-2006; modelo tipo Elo "**SUM**" desde
  **16-ago-2018**. Serie **no homogénea**. Desde 2026 hay actualización "**live**".
- **format / requires_api_key:** sin descarga oficial estructurada (CSV) confirmada. Terceros:
  Kaggle `cashncarry/fifaworldranking` (1992-2024) y GitHub `cnc8/fifa-world-ranking` (scraper).
- **license / legal_risk:** ToS de fifa.com **restrictivos** (licencia limitada, no comercial, sin
  redistribución; logos prohibidos sin permiso). El CC0 de los datasets terceros lo pone el uploader,
  **no FIFA** → no anula el copyright de FIFA. **No** versionar el dato crudo (solo script).
- **limitations:** snapshot exacto pre-torneo difícil de obtener (principal vía de leakage). Solo
  desde 1992.
- **use_in_project:** **feature opcional** + `fifa_ranking_baseline`, serie *as-of*. **Nota:** el
  ranking FIFA es además **criterio oficial de desempate** de grupos (addendum §7), por lo que se
  necesita su snapshot para simular grupos con fidelidad.
- **verification_status:** `VERIFIED (partial) — términos restrictivos`.

### 3.4 OpenFootball / worldcup.json

- **data_type:** datos estructurados de Mundiales (rondas, fechas, equipos, marcadores
  full/half/extra-time y penales, goleadores, grupo, sede).
- **temporal_coverage:** todos los Mundiales **1930–2026** (incluye 2026 Canadá/USA/México).
- **format:** JSON (repo `openfootball/worldcup.json`); commits ~1/día (**no** en vivo); historial
  de commits útil para snapshots.
- **license:** **CC0-1.0** (dominio público, sin atribución obligatoria) — confirmada.
- **use_in_project:** estructura de Mundiales (incl. fixtures 2026) y validación cruzada de
  `matches`. Fuente preferida por su licencia limpia.
- **verification_status:** `VERIFIED (2026-06-11)`.

### 3.5 StatsBomb Open Data (V2/V3, NO V1)

- **data_type:** event data (pases, tiros, xG). Selecciones: WC masculino 1958–2022 (parcial), WC
  femenino 2019/2023, Euro 2020/2024, Euro fem. 2022/2025, AFCON 2023, Copa América 2024, U20 1979.
  **No** incluye Mundial 2026.
- **license:** **NO es CC0** — "StatsBomb Public Data User Agreement" (`LICENSE.pdf`): uso público
  **no comercial**, con **atribución obligatoria** ("StatsBomb") y **logo**. Confirmado.
- **legal_risk:** alto si se versiona el crudo en repo público o se da carácter comercial.
- **use_in_project:** **excluida de V1.** En V2/V3, solo vía script de descarga (no versionar
  crudos) y con atribución+logo. Addendum §14.
- **verification_status:** `VERIFIED (license) — V2/V3`.

### 3.6 football-data.co.uk (V2/V3 — clubes, NO V1)

- **data_type:** resultados y **odds** de ligas de clubes.
- **use_in_project:** **excluida de V1** (es de clubes y trae odds; addendum §15). Posible contexto
  de jugadores en V2/V3.
- **verification_status:** `OUT OF SCOPE V1`.

### 3.7 Otras fuentes

Cualquier fuente adicional debe pasar **el mismo checklist** (licencia explícita, cobertura,
formato, ToS) antes de integrarse. **Sin licencia clara, no entra.**

---

## 4. Matriz fuente × cobertura (a completar en Phase 2)

| Fuente | Cobertura | Homogeneidad | Rol V1 |
|--------|-----------|--------------|--------|
| Kaggle results | ~1872→ | alta (resultados) | columna vertebral |
| Elo interno (derivado) | = cobertura de resultados | alta | feature de fuerza |
| FIFA ranking | 1992→ (cambio 2018) | **baja** (metodología cambió) | feature opcional + baseline |
| OpenFootball | Mundiales | media | validación estructura |
| StatsBomb | ediciones sueltas | baja | excluida V1 |

Política de missing-data: el FIFA ranking es feature **opcional con indicador de disponibilidad**,
no columna obligatoria; ninguna ventana exige una fuente que no cubra su rango.

---

## 5. Gobernanza y reproducibilidad de datos

- **Snapshots inmutables:** cada descarga → `data/raw/<source>/<YYYY-MM-DD>/` con manifest
  (`url`, `snapshot_date`, `upstream_version_or_commit`, `sha256`, `bytes`) registrado en
  `data_sources` + `ingestion_runs`.
- **Qué se versiona en git:** worldcup.json (si su licencia lo permite) y derivados propios, sí;
  FIFA ranking y StatsBomb crudos, **no** (solo scripts). `data/raw` en `.gitignore`.
- **Reconciliación entre fuentes:** `source_id` por fila + regla de precedencia documentada +
  validación (`pandera`) que marque conflictos (mismo partido con marcador/fecha distintos).
- **Idempotencia:** claves naturales UNIQUE + UPSERT por `ingestion_run`.

---

## 6. Reglamento oficial 2026 (VERIFICADO)

Verificado contra el documento oficial *Regulations for the FIFA World Cup 26* (Article 13 +
**Annex C**), `FWC2026_regulations_EN.pdf` (FIFA Digital Hub):

- **Desempates de grupos** (addendum §7): cascada verificada — puntos → head-to-head (puntos/DG/goles
  entre empatados) → DG global → goles global → **team conduct score** (disciplina) → ranking FIFA;
  **sin sorteo**. Novedad 2026: head-to-head **antes** que la DG global.
- **Mapeo de terceros a Round of 32** (addendum §6): **495 combinaciones** (C(12,8)) publicadas en el
  **Annex C**; cuadro bloqueado automáticamente al cerrar grupos (sin segundo sorteo); slots de
  1.º/2.º fijos (Match 73–88); ningún tercero repite rival de su grupo.

**verification_status:** `VERIFIED (2026-06-11)`. **Pendiente de implementación:** transcribir las
495 filas del Annex C a `third_place_bracket_mapping` desde el PDF oficial (el detalle celda-a-celda
no se extrajo del PDF; estructura confirmada vía fuentes secundarias).
