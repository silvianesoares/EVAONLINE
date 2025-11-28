# Study Area Map Generation

This document describes how to generate the study area map showing the validation cities used in the EVAonline validation dataset, with detailed climate zones and geographic context.

## Overview

The script `scripts/1_generate_matopiba_map.py` generates a professional two-panel map featuring:
- **Left Panel**: Brazil context map with MATOPIBA region highlighted
- **Right Panel**: Detailed MATOPIBA region with meteorological stations
- **Climate Zones**: Complete Köppen-Geiger climate classification overlay
- **Legend**: Three-column climate classification legend
- **Extras**: Scale bars, compass rose, and global location inset

## Data Sources

### Official Brazilian Geographic Data

1. **MATOPIBA Region Definition**
   - Source: MAGALHÃES, L. A.; MIRANDA, E. E. de. MATOPIBA: Quadro Natural. Campinas: Embrapa, 2014. (Embrapa. Nota Técnica GITE, 5). 41 p.
   - URL: https://www.infoteca.cnptia.embrapa.br/infoteca/handle/doc/1037412
   - File: `data/map_data/Matopiba_Perimetro.geojson`
   - Description: Technical note defining the natural framework of MATOPIBA region

2. **IBGE Climate Map of Brazil**
   - Source: IBGE. 2002. Mapa de Clima do Brasil.
   - Viewer: http://www.visualizador.inde.gov.br/
   - Downloads: https://www.ibge.gov.br/geociencias/informacoes-ambientais/climatologia/15817-clima.html?=&t=downloads
   - File: `data/map_data/shapefile_climate/clima_5000.shp`
   - Description: Official climate classification and boundaries for Brazil (Köppen-Geiger system)

3. **IBGE Geospatial Data**
   - File: `data/map_data/BR_UF_2024.geojson`
   - Content: States boundaries (Maranhão, Tocantins, Piauí, Bahia, São Paulo)
   - Description: Brazilian states boundaries (2024 version)

4. **Station Metadata**
   - File: `data/map_data/cities_plot.csv`
   - Content: Coordinates, names, and plot settings for validation cities
   - Format: CSV with columns: CITY, UF, LATITUDE, LONGITUDE, CODE_ST, PLOT

## Study Cities

The script automatically loads station data from `data/map_data/cities_plot.csv` and filters cities with `PLOT=YES`. The map displays cities from the MATOPIBA region plus one control site.

### MATOPIBA Region (16 cities):

**Maranhão (MA) - 4 cities:**
- Balsas: -7.532°, -46.036°
- Carolina: -7.334°, -47.467°
- Imperatriz: -5.526°, -47.479°
- Tasso Fragoso: -8.513°, -46.216°

**Tocantins (TO) - 4 cities:**
- Araguaína: -7.191°, -48.207°
- Campos Lindos: -7.991°, -46.866°
- Pedro Afonso: -8.969°, -48.173°
- Porto Nacional: -10.708°, -48.417°

**Piauí (PI) - 4 cities:**
- Alvorada do Gurguéia: -8.429°, -43.774°
- Bom Jesus: -9.077°, -44.358°
- Corrente: -10.439°, -45.161°
- Uruçuí: -7.234°, -44.549°

**Bahia (BA) - 4 cities:**
- Barreiras: -12.153°, -44.990°
- Formosa do Rio Preto: -11.047°, -45.195°
- Luiz Eduardo Magalhães: -12.095°, -45.802°
- São Desidério: -12.360°, -44.973°

### Control Site (1 city):

**São Paulo (SP), Brazil:**
- Piracicaba: -22.725°, -47.649°
  * Located outside MATOPIBA region
  * Historical reference data available

## Map Features

### Left Panel: Brazil Context Map
- **Geographic Extent**: -75° to -33° longitude, -35° to 6° latitude
- **Climate Zones**: Köppen-Geiger classification overlay (60+ climate types)
- **MATOPIBA Highlight**: Red border (1.5 linewidth)
- **State Boundaries**: Black lines (0.5 linewidth)
- **Ocean**: Natural blue color
- **Scale Bar**: 500 km (5 segments, alternating black/red)
- **Border**: 3.0 linewidth black frame
- **Grid**: Latitude/longitude labels (28pt font)

### Right Panel: MATOPIBA Detailed Map
- **Geographic Extent**: MATOPIBA bounds with margins (minx-6.5, maxx+0.2, miny-2.0, maxy+1.2)
- **Climate Zones**: Full Köppen-Geiger overlay
- **MATOPIBA Border**: Red line (6 linewidth)
- **Stations**: Numbered colored circles (1-17, size 500)
- **Station Labels**: Numbers with white outline (26pt font, +0.08° vertical offset)
- **Legend**: Upper-left corner with station list
- **Scale Bar**: 100 km (5 segments, 15 linewidth)
- **Grid**: Coordinate labels (28pt font)

### Additional Elements
- **Globe Inset**: Orthographic projection showing Brazil location (0.12×0.12 size)
- **Compass Rose**: Below Brazil map, centered (0.06 size)
- **Connection Arrows**: Black arrows linking context to detail maps
- **Climate Legend**: Three-column layout at bottom (32-34pt fonts)

### Color Palette
The script uses a comprehensive color mapping for 60+ climate zones:
- **Equatorial**: Purple shades (#6A339A, #A378B9, #D1AAD1, #E6D4E6)
- **Tropical Central Brazil**: Yellow to red (#FFFFBE → #F7941D)
- **Tropical Northeastern**: Similar gradient
- **Tropical Equatorial**: Extreme red (#ED1C24) for semi-arid
- **Temperate**: Blue shades (#00AEEF, #66C5EE)
- **Subhot**: Green shades (#8BC53F, #B5D69C, #00843D)

## Technical Implementation

### Python Dependencies
```python
import pandas as pd              # Data manipulation
import geopandas as gpd         # Geospatial data handling
import matplotlib.pyplot as plt  # Plotting
from matplotlib.gridspec import GridSpec  # Layout
import cartopy.crs as ccrs      # Cartographic projections
import cartopy.feature as cfeature  # Geographic features
import seaborn as sns           # Color palettes
import matplotlib.patheffects as PathEffects  # Text effects
from pathlib import Path        # File path handling
```

### Script Architecture
```
1_generate_matopiba_map.py
├── Configuration (lines 26-40)
│   ├── Dynamic paths using Path(__file__)
│   └── File validation checks
├── Functions (lines 66-446)
│   ├── normalize_text(): Climate name normalization
│   ├── get_color(): Climate-to-color mapping
│   ├── displace(): Geographic coordinate displacement
│   └── add_scalebar(): Scale bar drawing
├── Data Loading (lines 450-517)
│   ├── GeoJSON loading (Brazil, MATOPIBA)
│   ├── Shapefile loading (climate zones)
│   └── CSV loading (stations)
├── Figure Setup (lines 519-557)
│   ├── GridSpec layout (36×32 inches, 100 DPI)
│   └── Two subplots with projection
├── Left Panel Plotting (lines 559-618)
│   ├── Climate zones overlay
│   ├── Brazil boundaries
│   └── MATOPIBA highlight
├── Right Panel Plotting (lines 620-713)
│   ├── Climate zones
│   ├── Station points and labels
│   └── Legend
├── Extras (lines 757-905)
│   ├── Globe inset
│   ├── Connection arrows
│   ├── Scale bars
│   └── Compass rose
├── Climate Legend (lines 907-1045)
│   └── Three-column layout
└── Save (lines 1047-1050)
    └── PNG output (300 DPI)
```

### Key Functions

#### `normalize_text(text: str) -> str`
Normalizes climate descriptions by:
- Converting to lowercase
- Removing accents (á→a, é→e, etc.)
- Removing special characters
- Normalizing whitespace
- Used for climate name matching in color_map

#### `get_color(desc: str) -> str`
Maps climate descriptions to hex colors:
- Returns "#808080" for NaN values
- Returns "#E0E0E0" for unmapped climates
- Uses normalized_color_map for matching

#### `displace(lat, lon, az, dist_m) -> tuple`
Calculates destination coordinates:
- Implements Haversine formula
- Parameters: initial lat/lon, azimuth (degrees), distance (meters)
- Returns: (final_lat, final_lon) in degrees
- Used for drawing scale bars

#### `add_scalebar(ax, metric_distance, ...)`
Draws alternating colored scale bars:
- Segments: Alternating black/red
- Text: White outline for visibility
- Transform: Geodetic (accounts for Earth curvature)

## Output Specifications

### Generated File
- **Path**: `figures/study_area_map.png`
- **Format**: PNG
- **Resolution**: 300 DPI
- **Figure Size**: 36×32 inches (10,800×9,600 pixels)
- **Layout**: Two-panel with bottom legend
- **File Size**: ~15-25 MB (depending on compression)

### Usage Contexts

#### For README (Web Display):
- Resize to 800-1200 pixels width
- Maintain aspect ratio
- Optimize for web (reduce file size)

#### For Publication (SoftwareX):
- Use original 300 DPI resolution
- Dimensions: 10,800×9,600 pixels (as generated)
- No post-processing needed
- Meets journal requirements

#### For Graphical Abstract (Zenodo):
- Crop to single panel or key region
- Resize to 1328×531 pixels (Zenodo recommendation)
- Maintain aspect ratio if needed

### Quality Features
- **Vector-quality text**: All labels, titles, legends
- **High-resolution rasters**: Climate zone boundaries
- **Smooth gradients**: Color transitions in climate zones
- **Print-ready**: 300 DPI suitable for publication

## Usage Instructions

### Prerequisites

Install required Python packages:
```bash
# Using pip
pip install pandas geopandas matplotlib cartopy seaborn

# Or using conda
conda install pandas geopandas matplotlib cartopy seaborn
```

### Running the Script

```bash
# Navigate to the scripts directory
cd EVAonline_validation_v1.0.0/scripts/

# Run the script
python 1_generate_matopiba_map.py

# Output will be saved to:
# ../figures/study_area_map.png
```

### Expected Console Output
```
Starting the generation of the adjusted map with selected stations...
All required files found. Output: ../figures/study_area_map.png
Loading Brazil GeoJSON...
Brazil GeoJSON loaded successfully.
Loading MATOPIBA GeoJSON...
MATOPIBA GeoJSON loaded successfully.
Loading climate shapefile...
Climate shapefile loaded successfully.
Loading stations CSV...
Stations CSV loaded successfully.
Data loaded and processed. Total stations with PLOT=YES: 17
Figure created. Starting plotting...
Plotting climate layer for Brazil...
Total stations plotted with PLOT=YES: 17
Adding scale bar to MATOPIBA...
Adding scale bar to Brazil...
Plotting completed. Saving the file...

Adjusted map saved as '../figures/study_area_map.png'!
```

### Troubleshooting

**File not found errors:**
- Ensure you're running from `EVAonline_validation_v1.0.0/scripts/` directory
- Check that all data files exist in `../data/map_data/`

**Memory errors:**
- Reduce DPI from 100 to 50 in line 524: `fig = plt.figure(figsize=(36, 32), dpi=50)`
- Reduce figure size: `fig = plt.figure(figsize=(24, 21), dpi=100)`

**Projection errors:**
- Update Cartopy: `pip install --upgrade cartopy`
- Check PROJ data installation

## Citations

When using this map in publications, cite:

### Data Sources

**MATOPIBA Region Definition:**
```bibtex
@techreport{magalhaes2014matopiba,
  author = {Magalhães, L. A. and Miranda, E. E. de},
  title = {MATOPIBA: Quadro Natural},
  institution = {Embrapa},
  year = {2014},
  type = {Nota Técnica GITE},
  number = {5},
  pages = {41},
  address = {Campinas},
  url = {https://www.infoteca.cnptia.embrapa.br/infoteca/handle/doc/1037412}
}
```

**Brazil Climate Classification:**
```bibtex
@misc{ibge2002clima,
  author = {{IBGE}},
  title = {Mapa de Clima do Brasil},
  year = {2002},
  organization = {Instituto Brasileiro de Geografia e Estatística},
  url = {http://www.visualizador.inde.gov.br/}
}
```

**Xavier Reference Data:**
```bibtex
@article{xavier2016daily,
  author = {Xavier, Alexandre C. and King, Carey W. and Scanlon, Bridget R.},
  title = {Daily gridded meteorological variables in Brazil (1980-2013)},
  journal = {International Journal of Climatology},
  volume = {36},
  number = {6},
  pages = {2644-2659},
  year = {2016},
  doi = {10.1002/joc.4518}
}

@article{xavier2022new,
  author = {Xavier, Alexandre C. and Scanlon, Bridget R. and King, Carey W. and Alves, Ana I.},
  title = {New improved Brazilian daily weather gridded data (1961–2020)},
  journal = {International Journal of Climatology},
  volume = {42},
  number = {16},
  pages = {8390-8404},
  year = {2022},
  doi = {10.1002/joc.7731}
}
```

## Technical Notes

### MATOPIBA Region
- Brazil's newest agricultural frontier
- Encompasses 73 million hectares across 4 states
- Name origin: **MA**ranhão + **TO**cantins + **PI**auí + **BA**hia
- Key characteristics:
  - Transition zone between Amazon, Cerrado, and Caatinga biomes
  - Significant agricultural expansion since 1980s
  - Diverse climate zones (tropical, semi-arid, humid)

### Climate Classification
- System: Köppen-Geiger (IBGE 2002)
- Total zones mapped: 60+ types
- Main categories:
  - **Equatorial**: Hot, super-humid regions
  - **Tropical**: Central Brazil, Northeastern, Equatorial zones
  - **Temperate**: Mesothermic and subhot variants
- Temperature thresholds:
  - Hot: >18°C all months
  - Subhot: 15-18°C in at least one month
  - Mesothermic: 10-15°C average

### Coordinate System
- **Reference System**: WGS84 (EPSG:4326)
- **Map Projection**: PlateCarree (Equidistant Cylindrical)
- **Reason**: Optimal for mid-latitude regions like Brazil
- **Alternative**: Mercator for web applications

### File Structure
```
EVAonline_validation_v1.0.0/
├── scripts/
│   └── 1_generate_matopiba_map.py    # Main script
├── data/
│   └── map_data/
│       ├── cities_plot.csv           # Station metadata
│       ├── BR_UF_2024.geojson       # Brazil boundaries
│       ├── Matopiba_Perimetro.geojson  # MATOPIBA polygon
│       └── shapefile_climate/
│           └── clima_5000.shp       # Climate zones
├── figures/
│   └── study_area_map.png           # Output file
└── docs/
    └── study_area_map_generation.md  # This file
```

### Performance Considerations
- **Execution Time**: 30-60 seconds on modern hardware
- **Memory Usage**: ~2-4 GB during plotting
- **Bottlenecks**: Climate shapefile processing (60+ zones)
- **Optimization**: Pre-simplify geometries if faster rendering needed

### Customization Options

**Change DPI/Size:**
```python
# Line 524
fig = plt.figure(figsize=(36, 32), dpi=100)  # Adjust values
```

**Modify Color Scheme:**
```python
# Lines 97-297: color_map dictionary
# Change hex colors for different climate zones
```

**Add/Remove Stations:**
```python
# Edit data/map_data/cities_plot.csv
# Set PLOT column to "YES" or "NO"
```

**Adjust Map Extent:**
```python
# Line 607: Brazil extent
ax_context.set_extent([-75, -33, -35, 6], crs=PROJECTION)

# Line 697: MATOPIBA extent
ax_main.set_extent([minx - 6.5, maxx + 0.2, miny - 2.0, maxy + 1.2], ...)
```

---

**Script Version**: 1.0  
**Last Updated**: November 26, 2025  
**Author**: Ângela S. M. C. Soares, Prof. Carlos D. Maciel, Prof. Patricia A. A. Marques  
**Contact**: [EVAonline Project](https://github.com/silvianesoares/EVAONLINE)
