# 🌍 GeoFreak

**GeoFreak** es una plataforma web interactiva de juegos y exploración geográfica. Identifica países por su forma, bandera, estadísticas y mucho más.

## 🚀 Inicio rápido

### Requisitos
- Python 3.12+
- (Opcional) Docker & Docker Compose

### Instalación local

```bash
# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Copiar y configurar variables de entorno
cp .env.example .env

# Descargar datos (GeoJSON, banderas, dataset)
python scripts/download_data.py

# Ejecutar en local
python main.py
```

La app estará disponible en [http://localhost:8000](http://localhost:8000).

### Ejecución con Docker

```bash
# Build y arranque
python main.py --docker

# Forzar re-creación de contenedores
python main.py --docker --force-recreate
```

## 📁 Estructura del proyecto

```
contornos/
├── main.py                  # Entry point
├── routers/                 # FastAPI route handlers
│   ├── pages.py             # HTML page routes
│   └── api.py               # API JSON endpoints
├── services/                # Business logic
│   ├── dataset.py           # Dataset loader
│   └── geodata.py           # GeoJSON services
├── templates/               # Jinja2 HTML templates
│   ├── base.html
│   ├── landing.html
│   └── map.html
├── static/                  # Static files
│   ├── css/
│   ├── js/
│   ├── img/
│   └── data/
│       ├── countries.csv
│       ├── geojson/
│       └── images/flags/
├── scripts/                 # Data download scripts
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 📊 Datasets

El dataset principal contiene información de **todos los países del mundo**:
- Población, densidad, natalidad, inmigración
- Superficie, altitudes, coordenadas
- Nombres, capitales, ciudades principales
- PIB, PIB per cápita, Índice de Gini, IDH
- Religiones, idiomas oficiales, lenguas
- Banderas en formato SVG

## 🗺️ Mapa interactivo

Visualizador con Leaflet.js que incluye:
- Contornos GeoJSON de todos los países
- Hover con nombre y capital
- Click para modal con datos completos y bandera
- Capitales y ciudades principales marcadas
- Selector de capas (plano, satélite, estándar)

## 📜 Licencia

Proyecto educativo y de entretenimiento.
