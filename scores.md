# Sistema de puntuación y rankings — GeoFreak

## Contexto

El sistema de puntuación unifica los 7 juegos competitivos de GeoFreak en una arquitectura común, permitiendo rankings justos independientemente de las diferencias internas de cada juego.

### Juegos competitivos

| # | Juego | ID interno | Tipo de puntuación |
|---|-------|------------|--------------------|
| 1 | GeoFreaker | `comparison` | Binario (acierto/fallo) |
| 2 | GeoStats | `geostats` | Puntuación 0–10 por pregunta |
| 3 | GeoRankings | `ordering` | Puntuación 0–10 por pregunta |
| 4 | Adivinar banderas | `flags` | Binario |
| 5 | Adivinar contornos | `outline` | Binario |
| 6 | Desafío sobre el mapa | `map-challenge` | Binario |
| 7 | Rocas y agua | `relief-challenge` | Binario |

---

## Principio competitivo

**Solo el modo con tiempo (contrarreloj) entra en rankings competitivos** (`ranked = true`).

El modo sin tiempo es para práctica, mejora personal y exploración. No compite en rankings públicos.

---

## 1. Normalización de calidad (q)

Todos los juegos se convierten a una métrica de calidad normalizada $q \in [0, 1]$.

### Juegos binarios (flags, outline, comparison, map-challenge, relief-challenge)

$$q = \frac{\text{aciertos}}{\text{preguntas}}$$

### Juegos con puntuación 0..10 (geostats, ordering)

$$q = \frac{\sum x_i}{10 \cdot n}$$

donde $x_i$ es la puntuación de la pregunta $i$ (entre 0 y 10) y $n$ es el número de preguntas.

Equivalente a: $q = \frac{\text{promedio por pregunta}}{10}$

---

## 2. Score de intento (S)

### Componentes

| Componente | Fórmula | Propósito |
|------------|---------|-----------|
| Calidad | $Q = q^3$ | La precisión domina. Perder calidad penaliza claramente |
| Tiempo | $T = \frac{1}{1 + 0.35 \cdot \frac{t_{pp}}{t_{ref}}}$ | La velocidad mejora o desempata, pero es secundaria |
| Confianza | $C(n) = 1 - e^{-n/15}$ | Partidas cortas cuentan menos |

donde:
- $t_{pp} = t / n$ — tiempo por pregunta (segundos)
- $t_{ref}$ — tiempo de referencia por pregunta del test (de configuración)
- $n$ — número de preguntas

### Fórmula final

$$S = 1000 \cdot Q \cdot T \cdot C(n) = 1000 \cdot q^3 \cdot \frac{1}{1 + 0.35 \cdot \frac{t_{pp}}{t_{ref}}} \cdot \left(1 - e^{-n/15}\right)$$

### Tiempos de referencia por juego

| Juego | $t_{ref}$ (segundos) |
|-------|---------------------|
| flags, outline, comparison, ordering, geostats | 20 |
| map-challenge (type) | 4 |
| map-challenge (click) | 6 |
| relief-challenge (type) | 4 |
| relief-challenge (click) | 8 |

### Tabla de ejemplo (20 preguntas, $t_{ref} = 20$s)

| q | Tiempo total | S |
|-----|-------------|-----|
| 1.0 | 100s | 677 |
| 1.0 | 200s | 542 |
| 0.9 | 100s | 493 |
| 0.8 | 100s | 347 |
| 0.5 | 100s | 85 |

---

## 3. Récords absolutos

### Aplica especialmente a:
- **Desafío sobre el mapa** (`map-challenge`)
- **Rocas y agua** (`relief-challenge`)

Los récords se guardan **por configuración exacta** (dataset, continente, categoría, número de preguntas).

### Tipos de récord

| Tipo | Criterio | Desempates |
|------|----------|------------|
| **Calidad** | Mayor $q$ | $S$ desc → $t_{pp}$ asc → $n$ desc → fecha |
| **Score** | Mayor $S$ | — |
| **Perfecto** | Solo $q = 1.0$, menor $t_{pp}$ | $n$ desc → tiempo total asc → fecha |

### Clave de configuración

```
{game_type}:{dataset}:{continent}:{category}:{n}
```

Ejemplo: `map-challenge:countries:all:all:20`

---

## 4. Rating por prueba (R_test)

Cada intento ranked genera un score $S$ que se convierte en **percentil** $P$ dentro del histórico de esa prueba.

$$R_{test,nuevo} = (1 - \lambda) \cdot R_{test,viejo} + \lambda \cdot P$$

### Parámetros

| Parámetro | Valor | Condición |
|-----------|-------|-----------|
| $\lambda$ | 0.20 | Mejor intento del día |
| $\lambda$ | 0.05 | Intentos extra del mismo día con percentil inferior |

### Regla anti-spam

Solo el **mejor intento diario** por prueba actualiza $R_{test}$ con peso completo. Los intentos adicionales se guardan en historial y son aptos para récord, pero usan $\lambda = 0.05$.

---

## 5. Ranking por juego (RG)

Para cada jugador, dentro de un juego, se ordenan sus ratings por prueba de mayor a menor.

$$RG = R_1 + 0.85 \cdot R_2 + 0.70 \cdot R_3 + 0.55 \cdot R_4 + 0.40 \cdot R_5$$

### Bonus de amplitud

$$RG_{final} = RG \cdot \left(1 + 0.02 \cdot \min(10,\; \text{tests válidos} - 1)\right)$$

---

## 6. Ranking de temporada (12 semanas)

### Paso 1: Game rankings de temporada

Se calculan los rankings por juego usando solo partidas de las últimas 12 semanas. Se ordenan de mayor a menor: $G_1, G_2, G_3, G_4$.

### Paso 2: Fórmula base

$$RT = G_1 + 0.80 \cdot G_2 + 0.60 \cdot G_3 + 0.45 \cdot G_4$$

### Bonus

| Bonus | Fórmula |
|-------|---------|
| Variedad | $B_v = 1 + 0.04 \cdot \min(6,\; v - 1)$ |
| Constancia | $B_c = 1 + 0.02 \cdot \min(8,\; d - 1)$ |

donde $v$ = juegos activos, $d$ = semanas activas.

$$RT_{final} = RT \cdot B_v \cdot B_c$$

### Elegibilidad

- Mínimo 3 semanas activas **y** 2 juegos activos, **o**
- Mínimo 10 partidas ranked válidas en la ventana

---

## 7. Ranking semanal

Semana natural: lunes 00:00 a domingo 23:59 UTC.

### Paso 1: Mejor intento semanal por test → Percentil $P$

### Paso 2: Agrupar por juego

$$RWG = W_1 + 0.75 \cdot W_2 + 0.50 \cdot W_3 + 0.30 \cdot W_4$$

### Paso 3: Agrupar juegos

$$RS_{base} = H_1 + 0.80 \cdot H_2 + 0.60 \cdot H_3$$

### Bonus semanales

| Bonus | Fórmula |
|-------|---------|
| Variedad | $B_{v} = 1 + 0.05 \cdot \min(4,\; jw - 1)$ |
| Actividad | $B_{a} = 1 + 0.015 \cdot \min(20,\; pw - 1)$ |
| Regularidad | $B_{r} = 1 + 0.02 \cdot \min(5,\; dw - 1)$ |

donde $jw$ = juegos distintos, $pw$ = tests distintos, $dw$ = días activos.

$$RS_{final} = RS_{base} \cdot B_v \cdot B_a \cdot B_r$$

### Elegibilidad semanal

- Mínimo 3 tests distintos
- Mínimo 2 días activos
- Mínimo 2 juegos distintos **o** 1 juego con ≥ 2 tests

---

## 8. Jerarquía de desempate

### Récords (map-challenge, relief-challenge)
1. Mayor $q$ → 2. Mayor $S$ → 3. Menor $t_{pp}$ → 4. Mayor $n$ → 5. Fecha

### Ranking por juego
1. Mayor $RG_{final}$ → 2. Mejor $R_1$ → 3. Mejor $R_2$ → 4. Más tests → 5. Fecha

### Ranking de temporada
1. Mayor $RT_{final}$ → 2. Mayor $G_1$ → 3. Más juegos → 4. Más semanas → 5. Fecha

### Ranking semanal
1. Mayor $RS_{final}$ → 2. Mayor $RS_{base}$ → 3. Más juegos → 4. Más días → 5. Fecha

---

## Implementación técnica

### Tablas DynamoDB nuevas

| Tabla | PK | SK | GSI | Propósito |
|-------|----|----|-----|-----------|
| `ranked_attempts` | `test_key` (S) | `attempt_id` (S) | `user-time-index` (PK=`user_id`, SK=`created_at`) | Todos los intentos ranked |
| `test_ratings` | `user_id` (S) | `test_key` (S) | — | Rating EMA por usuario×prueba |
| `records` | `config_key` (S) | `record_sort` (S) | — | Récords por configuración |

Los rankings agregados se materializan en la tabla existente `leaderboards_cache`.

### Servicios

| Archivo | Responsabilidad |
|---------|----------------|
| `services/scoring.py` | Normalización, score S, percentiles, R_test, récords |
| `services/rankings.py` | Rankings por juego, temporada, semanal; materialización |

### Endpoints API

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/rankings/game/{game_type}` | Ranking por juego |
| GET | `/api/rankings/season` | Ranking de temporada (12 semanas) |
| GET | `/api/rankings/weekly?week=2026-W14` | Ranking semanal |
| GET | `/api/rankings/rebuild` | Reconstruir todos los rankings |
| GET | `/api/user/scoring` | Datos de scoring del usuario (ratings, attempts, game rankings) |
| GET | `/api/records/{config_key}` | Récords de una configuración |

### Flujo de datos

```
Partida finalizada (ranked=true)
  │
  ├─ compute_quality(game_type, score, total, avg_score)  →  q
  │
  ├─ compute_attempt_score(q, n, time, tref)              →  S
  │
  ├─ store attempt in ranked_attempts
  │
  ├─ compute_percentile(S, all_test_scores)               →  P
  │
  ├─ update_rating(R_test_old, P, λ)                      →  R_test
  │
  └─ check_records(config_key, q, S, tpp, n)              →  récords
```

La materialización de rankings se ejecuta periódicamente (o bajo demanda vía `/api/rankings/rebuild`):

```
test_ratings (scan) → game rankings (RG_final)
ranked_attempts (scan) → season rankings (RT_final)
ranked_attempts (scan) → weekly rankings (RS_final)
```

### Frontend

El campo `ranked: true|false` se envía desde el frontend basado en si el temporizador estaba activo (`timeLimit > 0`). Las partidas sin tiempo (`ranked: false`) se guardan normalmente en match history pero **no entran en el sistema competitivo**.

---

## 9. Desafío Diario — Rankings independientes

El desafío diario tiene su propia categoría de rankings, separada del sistema competitivo por juego. Solo una prueba al día, siempre con temporizador.

**Solo usuarios loggeados participan en rankings.**

### Score diario

Se calcula con las mismas fórmulas que los juegos individuales:

$$S = 1000 \cdot q^3 \cdot \frac{1}{1 + 0.35 \cdot \frac{t_{pp}}{t_{ref}}} \cdot \left(1 - e^{-n/15}\right)$$

donde $t_{ref}$ se toma del `secs_per_item` configurado para el desafío diario (por defecto 15s).

### Ranking diario

Clasificación del día: todos los participantes del día ordenados por $S$ descendente. Sin requisitos de elegibilidad.

### Ranking mensual (mes natural)

Para cada mes natural (Abril, Mayo, etc.):

$$R_{mensual} = \bar{S} \cdot B_{constancia}$$

donde:
- $\bar{S}$ = promedio de los scores $S$ del usuario en el mes
- $B_{constancia} = 1 + 0.5 \cdot \left(\frac{d_{jugados}}{d_{mes}}\right)^{0.7}$
- $d_{jugados}$ = días jugados en el mes
- $d_{mes}$ = días totales del mes

**Tabla de ejemplo (mes de 30 días, avg S = 400):**

| Días jugados | $B_{constancia}$ | $R_{mensual}$ |
|-------------|-----------------|---------------|
| 1 | 1.03 | 412 |
| 5 | 1.12 | 448 |
| 10 | 1.22 | 488 |
| 15 | 1.31 | 524 |
| 20 | 1.38 | 552 |
| 25 | 1.45 | 580 |
| 30 | 1.50 | 600 |

**Elegibilidad:** mínimo 3 días jugados en el mes.

### Ranking absoluto (all-time)

$$R_{abs} = R_{EMA} \cdot B_{constancia}$$

donde:
- $R_{EMA}$ = Media Móvil Exponencial de los scores diarios ($\alpha = 0.12$)
  - Para cada día jugado: $R = (1-\alpha) \cdot R + \alpha \cdot S$
  - Para cada día perdido: $R = R \cdot 0.995$ (decay muy suave)
- $B_{constancia} = 1 + 0.4 \cdot \left(\frac{d_{recientes}}{30}\right)^{0.6}$
- $d_{recientes}$ = días jugados en los últimos 30 días

**Propiedades del diseño:**
- Un score perfecto un solo día **no** supera a alguien que lleva 10+ días jugando bien
- Perder un día aplica un decay de solo 0.5% — no es catastrófico
- La EMA da más peso a actuaciones recientes
- El bonus de constancia premia la regularidad pero no domina sobre la calidad

**Elegibilidad:** mínimo 5 días jugados en total.

### Tabla DynamoDB

| Tabla | PK | SK | GSI | Propósito |
|-------|----|----|-----|-----------|
| `daily_scores` | `user_id` (S) | `date` (S) | `date-score-index` (PK=`date`, SK=`score_s` N) | Un registro por usuario×día |

Los rankings se materializan en `leaderboards_cache`.

### Endpoints API

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/rankings/daily/today?date=2026-04-03` | Ranking del día |
| GET | `/api/rankings/daily/monthly?month=2026-04` | Ranking mensual |
| GET | `/api/rankings/daily/absolute` | Ranking absoluto all-time |
| GET | `/api/rankings/daily/rebuild` | Reconstruir rankings diarios |
| GET | `/api/user/daily-scores?limit=30` | Scores diarios del usuario |

### Servicio

| Archivo | Responsabilidad |
|---------|----------------|
| `services/daily_rankings.py` | Scoring diario, rankings día/mes/absoluto, materialización |
