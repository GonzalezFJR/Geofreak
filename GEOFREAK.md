# GeoFreak

GeoFreak es una plataforma web de juegos de geografía multijugador. Los usuarios pueden jugar solos, retar a amigos en duelos o competir en torneos. Todo gira alrededor del conocimiento geográfico: países, capitales, banderas, mapas y estadísticas del mundo.

---

## Juegos

Los juegos están organizados en dos grandes categorías: **GeoGames** y **GeoQuiz**.

### GeoGames

Juegos de lógica y estadística geográfica. Se juegan en solitario y ponen a prueba la intuición y el conocimiento sobre datos del mundo real.

| Juego | Descripción |
|---|---|
| **GeoRankings** | Ordena 5 países según una estadística (población, PIB, superficie…). |
| **GeoFreaker** | Compara dos países y adivina cuál tiene un valor más alto en una estadística dada. |
| **GeoStats** | Observa la curva histórica de una estadística y adivina qué país se esconde detrás. |

### GeoQuiz

Juegos de reconocimiento e identificación de elementos geográficos. Se dividen en dos subcategorías:

#### Adivina cuál
Juegos en los que hay que identificar un país a partir de una imagen o forma.

| Juego | Descripción |
|---|---|
| **Adivinar banderas** | Identifica el país al que pertenece cada bandera. |
| **Adivinar por contorno** | Reconoce un país solo por la silueta de su territorio. |

#### Sobre el mapa
Juegos interactivos sobre un mapa mundial.

| Juego | Descripción |
|---|---|
| **Nombrar países (mapa)** | Haz clic en países del mapa e intenta escribir su nombre. |
| **Nombrar países (escribir)** | Escribe nombres de países y observa cómo se iluminan en el mapa. |
| **Nombrar capitales (mapa)** | Haz clic en un país e intenta escribir el nombre de su capital. |
| **Nombrar capitales (escribir)** | Escribe capitales y observa cómo se ilumina su país en el mapa. |

---

## Modos de juego

- **Solo** — juega a tu ritmo contra el tiempo o contra ti mismo.
- **Duelo** — reta a un amigo o a otro usuario en tiempo real. Gana quien termine primero con mejor puntuación.
- **Torneo** — competición por rondas eliminatorias entre varios jugadores.

No todos los juegos están disponibles en todos los modos. Los GeoGames (GeoRankings, GeoFreaker, GeoStats) son exclusivamente de modo solo; los GeoQuiz admiten duelos y torneos.

---

## Vistas principales

| Ruta | Descripción |
|---|---|
| `/` | Página de inicio. Presenta la plataforma, sus modos y botones de acceso. |
| `/games` | Panel de juegos. Muestra todos los juegos organizados por categoría. |
| `/games/<id>` | Pantalla de configuración y juego para un juego concreto. |
| `/duels` | Selector de duelos. Permite crear o unirse a un duelo. |
| `/tournaments` | Selector de torneos. Permite crear o unirse a un torneo. |
| `/leaderboard` | Tabla de clasificación global y por juego. |
| `/profile` | Perfil del usuario: estadísticas, mejores puntuaciones, foto y ajustes de cuenta. |
| `/friends` | Lista de amigos, solicitudes pendientes y búsqueda de usuarios. |
| `/login` / `/register` | Autenticación: inicio de sesión y registro. |
| `/admin` | Panel de administración (solo administradores). Usuarios, estadísticas, juegos. |

---

## Usuarios y cuentas

- **Registro** por email y contraseña. Se envía un email de verificación al registrarse.
- **Planes**: free y premium (el plan determina el acceso a ciertas funcionalidades).
- **Perfil**: nombre de usuario, avatar (foto de perfil cuadrada), email, estadísticas y mejores puntuaciones por juego.
- **Estadísticas**: partidas jugadas, victorias, racha, puntuación ELO/rating, precisión.
- **Amigos**: sistema de solicitudes de amistad. Se puede buscar usuarios y ver su perfil público.
- **Idiomas**: la interfaz está disponible en español, inglés, francés, italiano y ruso.

---

## Puntuación y ranking

Cada partida genera una puntuación según respuestas correctas, velocidad y dificultad. Las puntuaciones se almacenan por juego, lo que permite ver los mejores registros de cada modalidad en el perfil.

Hay una tabla de clasificación global (/leaderboard) que refleja el rendimiento acumulado de todos los usuarios.

Existe además un **reto diario** (Daily Challenge), una partida predefinida de GeoFreaker disponible para todos los usuarios cada día.
