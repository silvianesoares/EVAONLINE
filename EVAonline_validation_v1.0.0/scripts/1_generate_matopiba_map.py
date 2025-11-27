# Matopiba Cities Map: Script to generate a two-panel map showing Brazil and the MATOPIBA region,
# With climate zones, meteorological stations, and a climate legend.
# Author: Ângela S. M. C. Soares, Profº Carlos D. Maciel and Profª Patricia A. A. Marques
# Date: July 10, 2025
# Output: study_area_map.png


import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches
from matplotlib.patches import ConnectionPatch
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import re
import seaborn as sns
import math
import matplotlib.patheffects as PathEffects


# --- 0. FILE PATHS AND CONFIGURATION ---
# Defines paths for data files and the output map.
META_CSV_PATH = "./EVAonline_validation_v1.0.0/data/map_data/cities_plot.csv"
BRASIL_GEOJSON_PATH = (
    "./EVAonline_validation_v1.0.0/data/map_data/BR_UF_2024.geojson"
)
MATOPIBA_GEOJSON_PATH = (
    "./EVAonline_validation_v1.0.0/data/map_data/Matopiba_Perimetro.geojson"
)
CLIMATE_SHAPEFILE_PATH = "./EVAonline_validation_v1.0.0/data/map_data/shapefile_climate/clima_5000.shp"
CLIMATE_COLUMN_NAME = (
    "DESC_COMPL"  # Column in the shapefile with climate descriptions
)
OUTPUT_MAP_PATH = "./EVAonline_validation_v1.0.0/figures/study_area_map.png"  # Output map file
# --- END OF CONFIGURATION ---

print("Starting the generation of the adjusted map with selected stations...")


# --- 1. FUNCTIONS AND COLOR PALETTE ---
def normalize_text(text):
    """Normalizes text by removing accents, special characters, and extra spaces.

    Args:
        text (str): Text to be normalized.

    Returns:
        str: Normalized text in lowercase, without accents or special characters.
    """
    if not isinstance(text, str):
        return ""
    text = text.lower().replace("º", " ").replace("°", " ")
    text = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )
    text = text.replace("â", "a").replace("ê", "e")
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Defines a color mapping for climate zones based on their descriptions.
color_map = {
    "Equatorial, quente - média > 18° C em todos os meses, super-úmido sem seca": "#6A339A",
    "Equatorial, quente - média > 18° C em todos os meses, super-úmido subseca": "#A378B9",
    "Equatorial, quente - média > 18° C em todos os meses, úmido 1 a 2 meses secos": "#D1AAD1",
    "Equatorial, quente - média > 18° C em todos os meses, úmido 3 meses secos": "#E6D4E6",
    "Equatorial, subquente - média entre 15 e 18 ° C em pelo menos 1 mês, super-úmido subseca": "#00A651",
    "Equatorial, subquente - média entre 15 e 18 ° C em pelo menos 1 mês, úmido 1 a 2 meses secos": "#8BC53F",
    "Equatorial, subquente - média entre 15 e 18 ° C em pelo menos 1 mês, úmido 3 meses secos": "#B5D69C",
    "Massa d'água": "#aadaff",
    "Temperado, mesotérmico brando - média entre 10 e 15° C, super-úmido sem seca": "#00AEEF",
    "Temperado, mesotérmico brando - média entre 10 e 15° C, super-úmido subseca": "#66C5EE",
    "Temperado, mesotérmico mediano - média > 10° C, super-úmido subseca": "#B3B3B3",
    "Temperado, subquente - média entre 15 e 18 ° C em pelo menos 1 mês, super-úmido sem seca": "#00843D",
    "Temperado, subquente - média entre 15 e 18 ° C em pelo menos 1 mês, super-úmido subseca": "#00A651",
    "Tropical Brasil Central, mesotérmico brando - média entre 10 e 15° C, semi-úmido 4 a 5 meses": "#E6F5FB",
    "Tropical Brasil Central, mesotérmico brando - média entre 10 e 15° C, super-úmido sem seca": "#00AEEF",
    "Tropical Brasil Central, mesotérmico brando - média entre 10 e 15° C, super-úmido subseca": "#66C5EE",
    "Tropical Brasil Central, mesotérmico brando - média entre 10 e 15° C, úmido 1 a 2 meses secos": "#99D9F2",
    "Tropical Brasil Central, mesotérmico brando - média entre 10 e 15° C, úmido 3 meses secos": "#CCEBF7",
    "Tropical Brasil Central, mesotérmico mediano - média > 10° C, super-úmido sem seca": "#808080",
    "Tropical Brasil Central, mesotérmico mediano - média > 10° C, úmido 1 a 2 meses secos": "#D9D9D9",
    "Tropical Brasil Central, quente - média > 18° C em todos os meses, semi-árido 6 meses secos": "#FFFFBE",
    "Tropical Brasil Central, quente - média > 18° C em todos os meses, semi-árido 7 a 8 meses secos": "#FFFF00",
    "Tropical Brasil Central, quente - média > 18° C em todos os meses, semi-árido 9 a 10 meses secos": "#F7941D",
    "Tropical Brasil Central, quente - média > 18° C em todos os meses, semi-úmido 4 a 5 meses secos": "#F2EFF2",
    "Tropical Brasil Central, quente - média > 18° C em todos os meses, super-úmido sem seca": "#6A339A",
    "Tropical Brasil Central, quente - média > 18° C em todos os meses, super-úmido subseca": "#A378B9",
    "Tropical Brasil Central, quente - média > 18° C em todos os meses, úmido 1 a 2 meses secos": "#D1AAD1",
    "Tropical Brasil Central, quente - média > 18° C em todos os meses, úmido 3 meses secos": "#E6D4E6",
    "Tropical Brasil Central, subquente - média entre 15 e 18 ° C em pelo menos 1 mês, semi-árido 6 meses secos": "#EFF6E9",
    "Tropical Brasil Central, subquente - média entre 15 e 18 ° C em pelo menos 1 mês, semi-úmido 4 a 5 meses secos": "#D9EAD3",
    "Tropical Brasil Central, subquente - média entre 15 e 18 ° C em pelo menos 1 mês, úmido 1 a 2 meses secos": "#8BC53F",
    "Tropical Brasil Central, subquente - média entre 15 e 18 ° C em pelo menos 1 mês, úmido 3 meses secos": "#B5D69C",
    "Tropical Brasil Central, subquente - média entre 15 e 18º C em pelo menos 1 mês, super-úmido sem seca": "#00843D",
    "Tropical Brasil Central, subquente - média entre 15 e 18º C em pelo menos 1 mês, super-úmido subseca": "#00A651",
    "Tropical Nordeste Oriental, quente - média > 18 ° C em todos os meses, semi-úmido 4 a 5 meses secos": "#F2EFF2",
    "Tropical Nordeste Oriental, quente - média > 18° C em todos os meses, semi-árido 6 meses secos": "#FFFFBE",
    "Tropical Nordeste Oriental, quente - média > 18° C em todos os meses, semi-árido 7 a 8 meses secos": "#FFFF00",
    "Tropical Nordeste Oriental, quente - média > 18° C em todos os meses, semi-árido 9 a 10 meses secos": "#F7941D",
    "Tropical Nordeste Oriental, quente - média > 18° C em todos os meses, super-úmido sem seca": "#6A339A",
    "Tropical Nordeste Oriental, quente - média > 18° C em todos os meses, super-úmido subseca": "#A378B9",
    "Tropical Nordeste Oriental, quente - média > 18º C em todos os meses, úmido 1 a 2 meses secos": "#D1AAD1",
    "Tropical Nordeste Oriental, quente - média > 18º C em todos os meses, úmido 3 meses secos": "#E6D4E6",
    "Tropical Nordeste Oriental, subquente - média entre 15 e 18 ° C em pelo menos 1 mês, semi-úmido 4 a 5 meses secos": "#D9EAD3",
    "Tropical Nordeste Oriental, subquente - média entre 15 e 18º C em pelo menos 1 mês, úmido 3 meses secos": "#B5D69C",
    "Tropical Zona Equatorial, quente - média > 18° C em todos os meses, semi-árido 11 meses secos": "#ED1C24",
    "Tropical Zona Equatorial, quente - média > 18° C em todos os meses, semi-árido 6 meses secos": "#FFFFBE",
    "Tropical Zona Equatorial, quente - média > 18° C em todos os meses, semi-árido 7 a 8 meses secos": "#FFFF00",
    "Tropical Zona Equatorial, quente - média > 18° C em todos os meses, semi-árido 9 a 10 meses secos": "#F7941D",
    "Tropical Zona Equatorial, quente - média > 18° C em todos os meses, semi-úmido 4 a 5 meses secos": "#F2EFF2",
    "Tropical Zona Equatorial, quente - média > 18° C em todos os meses, super-úmido subseca": "#A378B9",
    "Tropical Zona Equatorial, quente - média > 18° C em todos os meses, úmido 1 a 2 meses secos": "#D1AAD1",
    "Tropical Zona Equatorial, quente - média > 18° C em todos os meses, úmido 3 meses secos": "#E6D4E6",
    "Zona Contígua": "#ADD8E6",
    "Zona Costeira": "#ADD8E6",
    "Zona Exclusiva": "#ADD8E6",
}
normalized_color_map = {normalize_text(k): v for k, v in color_map.items()}


def get_color(desc):
    """Maps normalized climate descriptions to colors.

    Args:
        desc (str): Climate description from the shapefile.

    Returns:
        str: Hexadecimal color code corresponding to the description or default gray (#E0E0E0) if not found.
    """
    if pd.isna(desc):
        return "#808080"
    return normalized_color_map.get(normalize_text(desc), "#E0E0E0")


def blank_axes(ax):
    """Configures an axis to hide borders, ticks, and labels.

    Args:
        ax (matplotlib.axes.Axes): Axis to be configured.
    """
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.yaxis.set_ticks_position("none")
    ax.xaxis.set_ticks_position("none")
    ax.tick_params(
        labelbottom="off",
        labeltop="off",
        labelleft="off",
        labelright="off",
        bottom="off",
        top="off",
        left="off",
        right="off",
    )


def displace(lat, lon, az, dist_m):
    """Calculates final coordinates (latitude, longitude) from an initial point, azimuth, and distance.

    Args:
        lat (float): Initial latitude in degrees.
        lon (float): Initial longitude in degrees.
        az (float): Azimuth in degrees.
        dist_m (float): Distance in meters.

    Returns:
        tuple: (final latitude, final longitude) in degrees.
    """
    R = 6371e3  # Earth's radius in meters
    d = dist_m

    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    brng = math.radians(az)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(d / R)
        + math.cos(lat1) * math.sin(d / R) * math.cos(brng)
    )

    lon2 = lon1 + math.atan2(
        math.sin(brng) * math.sin(d / R) * math.cos(lat1),
        math.cos(d / R) - math.sin(lat1) * math.sin(lat2),
    )

    return math.degrees(lat2), math.degrees(lon2)


def add_scalebar(
    ax,
    metric_distance,
    bar_offset=(0.05, 0.05, 0.07),
    max_stripes=5,
    bar_alpha=0.3,
    fontsize=28,
    linewidth=10,
):
    """Adds a scale bar to the map axis.

    Args:
        ax (cartopy.mpl.geoaxes.GeoAxes): Map axis.
        metric_distance (float): Total length of the bar in meters.
        bar_offset (tuple): (x_offset, y_offset, text_offset) as a fraction of the axis.
        max_stripes (int): Number of segments in the bar.
        bar_alpha (float): Transparency of the bar.
        fontsize (int): Font size of the scale text.
        linewidth (float): Line width of the bar.

    Note: The linewidth=20 for the MATOPIBA scale bar does not render as expected,
          possibly due to rendering limitations in Cartopy/Matplotlib.
    """
    print(
        f"Adding scale bar to axis {ax.get_title()} with total length of {metric_distance / 1000} km and linewidth={linewidth}"
    )
    lon0, lon1, lat0, lat1 = ax.get_extent(crs=ccrs.PlateCarree())
    bar_lon0 = lon0 + (lon1 - lon0) * bar_offset[0]
    bar_lat0 = lat0 + (lat1 - lat0) * bar_offset[1]
    text_lon0 = bar_lon0
    text_lat0 = lat0 + (lat1 - lat0) * bar_offset[2]
    bar_tickmark = (
        metric_distance / max_stripes
    )  # Distance in meters per segment
    bar_ticks = max_stripes
    bar_color = ["black", "red"]
    for i in range(bar_ticks):
        end_lat, end_lon = displace(bar_lat0, bar_lon0, 90, bar_tickmark)
        print(
            f"Drawing scale bar segment {i+1} with linewidth={linewidth}, from ({bar_lon0:.4f}, {bar_lat0:.4f}) to ({end_lon:.4f}, {end_lat:.4f})"
        )
        ax.plot(
            [bar_lon0, end_lon],
            [bar_lat0, end_lat],
            color=bar_color[i % 2],
            linewidth=linewidth,
            transform=ccrs.Geodetic(),
            solid_capstyle="butt",
            alpha=bar_alpha,
            zorder=20,
        )
        bar_lon0 = end_lon
        bar_lat0 = end_lat
    buffer = [PathEffects.withStroke(linewidth=3, foreground="white")]
    total_distance_km = int(bar_ticks * bar_tickmark / 1000)
    ax.text(
        text_lon0,
        text_lat0,
        f"{total_distance_km} km",
        transform=ccrs.Geodetic(),
        horizontalalignment="left",
        verticalalignment="bottom",
        path_effects=buffer,
        zorder=21,
        fontsize=fontsize,
    )
    print(
        f"Scale bar drawn: {total_distance_km} km with {max_stripes} segments of {bar_tickmark / 1000} km each"
    )


# --- 2. GEOSPATIAL DATA PREPARATION ---
# Defines the cartographic projection (PlateCarree) for all maps.
PROJECTION = ccrs.PlateCarree()

# --- 2. GEOSPATIAL DATA PREPARATION ---
# Defines the cartographic projection (PlateCarree) for all maps.
PROJECTION = ccrs.PlateCarree()

try:
    # Loads geospatial data and converts to the EPSG:4326 coordinate system.
    print("Carregando GeoJSON do Brasil...")
    gdf_brasil = gpd.read_file(BRASIL_GEOJSON_PATH).to_crs(
        epsg=4326
    )  # Brazil's state boundaries
    print("GeoJSON do Brasil carregado com sucesso.")

    print("Carregando GeoJSON do MATOPIBA...")
    gdf_matopiba = gpd.read_file(MATOPIBA_GEOJSON_PATH).to_crs(
        epsg=4326
    )  # MATOPIBA perimeter
    print("GeoJSON do MATOPIBA carregado com sucesso.")

    print("Carregando shapefile de clima...")
    gdf_clima = gpd.read_file(CLIMATE_SHAPEFILE_PATH)  # Climate zones
    print("Shapefile de clima carregado com sucesso.")
    if gdf_clima.crs is None:
        gdf_clima.set_crs(epsg=4674, inplace=True)  # Sets CRS if not specified
    gdf_clima = gdf_clima.to_crs(epsg=4326)

    print("Carregando CSV de estações...")
    meta_df = pd.read_csv(
        META_CSV_PATH, sep=";", encoding="utf-8"
    )  # Explicitly set UTF-8
    print("CSV de estações carregado com sucesso.")

    meta_df["CODE_ST"] = meta_df["CODE_ST"].astype(
        str
    )  # Converts station code to string
    meta_df = meta_df[
        meta_df["PLOT"] == "YES"
    ]  # Filters stations for plotting
    # Sorts by city and assigns sequential numbers (1 to 16) and unique colors.
    meta_df = meta_df.sort_values(by="CITY")
    meta_df["number"] = range(1, len(meta_df) + 1)
    colors = sns.color_palette(
        "tab20", len(meta_df)
    )  # Color palette for stations
    meta_df["color"] = colors
    gdf_stations = gpd.GeoDataFrame(
        meta_df,
        geometry=gpd.points_from_xy(meta_df.LONGITUDE, meta_df.LATITUDE),
        crs="EPSG:4326",
    )
    print(
        f"Dados carregados e processados. Total de estações com PLOT=YES: {len(gdf_stations)}"
    )
except Exception as e:
    print(f"ERRO ao carregar ou processar arquivos. Detalhes: {e}")
    exit()

# --- 3. FIGURE SETUP WITH ADVANCED LAYOUT (GRIDSPEC) ---
# Creates a figure with size 36x32 inches and DPI 100 (reduced for rendering tests).
fig = plt.figure(figsize=(36, 32), dpi=100)
# Defines a layout with two rows: maps in the first, legend in the second.
gs_main_layout = GridSpec(2, 1, figure=fig, height_ratios=[10, 1], hspace=0.50)
# Splits the first row into two panels: Brazil (left) and MATOPIBA (right).
gs_map_layout = gs_main_layout[0, 0].subgridspec(
    1, 2, width_ratios=[1, 1.3], wspace=0.15
)
ax_context = fig.add_subplot(
    gs_map_layout[0], projection=PROJECTION
)  # Axis for the Brazil map
ax_main = fig.add_subplot(
    gs_map_layout[1], projection=PROJECTION
)  # Axis for the MATOPIBA map

print("Figure created. Starting plotting...")

# Adds an outer black border around the entire figure.
left_margin = 0.03
right_margin = 0.03
bottom_margin = 0.03
top_margin = 0.12
border_patch = mpatches.Rectangle(
    (left_margin, bottom_margin),
    1 - left_margin - right_margin,
    1 - bottom_margin - top_margin,
    linewidth=6,
    edgecolor="black",
    facecolor="none",
    transform=fig.transFigure,
    zorder=0,
)
fig.add_artist(border_patch)

# --- 4. LEFT PANEL: CONTEXT MAP (BRAZIL) ---
# Configures the Brazil map with climate zones and MATOPIBA highlight.
ax_context.set_title("Study Area Location", fontsize=42, fontweight="bold")
ax_context.add_feature(
    cfeature.OCEAN.with_scale("50m"), zorder=0
)  # Adds ocean
ax_context.add_feature(
    cfeature.BORDERS.with_scale("50m"),
    linestyle="-",
    edgecolor="black",
    linewidth=0.7,
    zorder=3,
)  # Adds borders

print("Plotting climate layer for Brazil...")
# Plots climate zones with colors defined by color_map.
for _, row in gdf_clima.iterrows():
    color = get_color(row[CLIMATE_COLUMN_NAME])
    gpd.GeoSeries([row.geometry]).plot(
        ax=ax_context, color=color, alpha=0.8, transform=PROJECTION, zorder=1
    )

gdf_brasil.plot(
    ax=ax_context,
    facecolor="none",
    edgecolor="black",
    linewidth=0.5,
    zorder=10,
    transform=PROJECTION,
)  # State boundaries
gdf_matopiba.plot(
    ax=ax_context,
    facecolor="none",
    edgecolor="red",
    linewidth=1.5,
    transform=PROJECTION,
    zorder=4,
)  # MATOPIBA border

# Sets the black border of the Brazil map square.
for spine in ax_context.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(3.0)  # Black border thickness
    spine.set_edgecolor("black")

# Sets the geographic extent of the Brazil map.
ax_context.set_extent([-75, -33, -35, 6], crs=PROJECTION)
# Adds grid with latitude and longitude labels.
gl = ax_context.gridlines(
    draw_labels=True,
    dms=True,
    x_inline=False,
    y_inline=False,
    linestyle=":",
    color="black",
    alpha=0.4,
)
gl.top_labels = False
gl.right_labels = False
gl.xlabel_style = {"size": 28, "color": "black"}
gl.ylabel_style = {"size": 28, "color": "black"}

# --- 5. RIGHT PANEL: MAIN MAP (MATOPIBA REGION) ---
# Configures the MATOPIBA map with climate zones, meteorological stations, and legend.
ax_main.set_title("MATOPIBA Region", fontsize=42, fontweight="bold")
# Sets the black border of the MATOPIBA map square.
for spine in ax_main.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(3.0)  # Black border thickness
    spine.set_edgecolor("black")
ax_main.add_feature(
    cfeature.OCEAN.with_scale("10m"), facecolor="#D6EAF8", zorder=0
)  # Adds ocean

# Plots climate zones.
for _, row in gdf_clima.iterrows():
    color = get_color(row[CLIMATE_COLUMN_NAME])
    gpd.GeoSeries([row.geometry]).plot(
        ax=ax_main, color=color, alpha=0.8, transform=PROJECTION, zorder=1
    )

gdf_brasil.plot(
    ax=ax_main,
    facecolor="none",
    edgecolor="black",
    linewidth=0.5,
    zorder=10,
    transform=PROJECTION,
)  # State boundaries
gdf_matopiba.plot(
    ax=ax_main,
    facecolor="none",
    edgecolor="red",
    linewidth=6,
    linestyle="-",
    transform=PROJECTION,
    zorder=5,
)  # MATOPIBA border

# Plots meteorological stations as colored points with black edges.
sns.scatterplot(
    ax=ax_main,
    data=gdf_stations,
    x=gdf_stations.geometry.x,
    y=gdf_stations.geometry.y,
    hue="number",
    palette=colors,
    marker="o",
    s=500,  # Point size
    edgecolor="black",
    linewidth=1.0,
    transform=PROJECTION,
    zorder=5,
)

# Adds numbers on stations with white outline for readability.
for idx, row in gdf_stations.iterrows():
    ax_main.text(
        row.geometry.x,
        row.geometry.y + 0.08,  # Vertical offset
        str(row["number"]),
        fontsize=26,
        ha="center",
        va="bottom",
        color="black",
        transform=PROJECTION,
        path_effects=[PathEffects.withStroke(linewidth=3, foreground="white")],
        zorder=6,
    )

# Verifies the number of stations plotted.
print(f"Total stations plotted with PLOT=YES: {len(gdf_stations)}")

# Sets the geographic extent of the MATOPIBA map with adjusted margins.
minx, miny, maxx, maxy = gdf_matopiba.total_bounds
ax_main.set_extent(
    [minx - 6.5, maxx + 0.2, miny - 2.0, maxy + 1.2], crs=PROJECTION
)
# Adds grid with latitude and longitude labels.
gl = ax_main.gridlines(
    draw_labels=True,
    dms=True,
    x_inline=False,
    y_inline=False,
    linestyle=":",
    color="black",
    alpha=0.4,
)
gl.top_labels = False
gl.right_labels = False
gl.xlabel_style = {"size": 28, "color": "black"}
gl.ylabel_style = {"size": 28, "color": "black"}

# Adds legend with MATOPIBA boundaries and stations in the upper-left corner.
h_matopiba = [
    mpatches.Patch(
        edgecolor="black",
        facecolor="none",
        linewidth=3,
        label="State Boundaries",
    ),
    mpatches.Patch(
        edgecolor="red",
        facecolor="none",
        linewidth=3,
        label="Matopiba Boundary",
    ),
]
h_cities = [
    Line2D(
        [0],
        [0],
        marker="o",
        color="w",
        markerfacecolor=row["color"],
        markersize=30,
        linestyle="None",
        label=f"{row['number']}. {row['CITY']}, {row['UF']}",
    )
    for idx, row in gdf_stations.iterrows()
]
legend = ax_main.legend(
    handles=h_matopiba + h_cities,
    title="MATOPIBA and Stations",
    loc="upper left",
    fontsize=24,
    title_fontsize=26,
    frameon=True,
    framealpha=0.9,
    edgecolor="black",
    bbox_to_anchor=(0.01, 0.98),
    handleheight=1.5,
    labelspacing=0.8,
)
legend.get_title().set_weight("bold")

# --- 6. ADD GLOBE, ARROWS, SCALE, AND COMPASS ROSE ---
# Adds a globe showing the location of Brazil and MATOPIBA.
ax_globe = fig.add_axes(
    [0.12, 0.48, 0.12, 0.12], projection=ccrs.Orthographic(-60, -15)
)
ax_globe.add_feature(cfeature.OCEAN, facecolor="#D6EAF8", zorder=0)
ax_globe.add_feature(cfeature.BORDERS, linestyle="-")
ax_globe.add_feature(
    cfeature.LAND, facecolor="lightgray", edgecolor="black", zorder=1
)
ax_globe.set_global()
gdf_brasil.plot(
    ax=ax_globe,
    facecolor="gray",
    edgecolor="black",
    linewidth=1.5,
    transform=PROJECTION,
    zorder=2,
)
gdf_matopiba.plot(
    ax=ax_globe,
    facecolor="none",
    edgecolor="red",
    linewidth=1.5,
    alpha=0.8,
    transform=PROJECTION,
    zorder=3,
)

# Adds a red rectangle on the Brazil map to highlight MATOPIBA.
rect = mpatches.Rectangle(
    (minx, miny),
    maxx - minx,
    maxy - miny,
    fill=False,
    edgecolor="red",
    linewidth=3,
    transform=PROJECTION,
    zorder=5,
)
ax_context.add_patch(rect)

# Adds connection lines between the Brazil and MATOPIBA maps.
con_kwargs = {
    "color": "black",
    "linewidth": 3,
    "arrowstyle": "->",
    "mutation_scale": 20,
}
con1 = ConnectionPatch(
    xyA=(minx, maxy + 0.5),
    xyB=(minx - 6.5, maxy + 1.2),
    coordsA=ax_context.transData,
    coordsB=ax_main.transData,
    zorder=40,
    **con_kwargs,
)
con2 = ConnectionPatch(
    xyA=(minx, miny - 0.5),
    xyB=(minx - 6.5, miny - 2.0),
    coordsA=ax_context.transData,
    coordsB=ax_main.transData,
    zorder=20,
    **con_kwargs,
)
fig.add_artist(con1)
fig.add_artist(con2)

# Adds scale bars to the Brazil (500 km) and MATOPIBA (100 km) maps.
print("Adding scale bar to MATOPIBA...")
add_scalebar(
    ax_main,
    metric_distance=100000,
    bar_offset=(0.05, 0.05, 0.07),
    max_stripes=5,
    bar_alpha=0.3,
    fontsize=30,
    linewidth=20,
)  # Note: linewidth=20 did not work as expected
print("Adding scale bar to Brazil...")
add_scalebar(
    ax_context,
    metric_distance=500000,
    bar_offset=(0.05, 0.05, 0.07),
    max_stripes=5,
    bar_alpha=0.3,
    fontsize=24,
    linewidth=10,
)


def add_compass(ax, pos_x, pos_y, size=0.1):
    """Adds a compass rose to the map.

    Args:
        ax (cartopy.mpl.geoaxes.GeoAxes): Map axis.
        pos_x (float): X position of the compass rose.
        pos_y (float): Y position of the compass rose.
        size (float): Size of the compass rose.
    """
    ax_compass = fig.add_axes([pos_x, pos_y, size, size], anchor="C")
    ax_compass.set_aspect("equal")
    ax_compass.axis("off")

    # Draws arrows for cardinal directions.
    ax_compass.arrow(
        0.5,
        0.8,
        0,
        -0.4,
        head_width=0.05,
        head_length=0.1,
        fc="black",
        ec="black",
        lw=1,
    )
    ax_compass.arrow(
        0.5,
        0.2,
        0,
        0.4,
        head_width=0.05,
        head_length=0.1,
        fc="black",
        ec="black",
        lw=1,
    )
    ax_compass.arrow(
        0.2,
        0.5,
        0.4,
        0,
        head_width=0.05,
        head_length=0.1,
        fc="black",
        ec="black",
        lw=1,
    )
    ax_compass.arrow(
        0.8,
        0.5,
        -0.4,
        0,
        head_width=0.05,
        head_length=0.1,
        fc="black",
        ec="black",
        lw=1,
    )

    # Adds labels for directions (N, S, E, W).
    ax_compass.text(0.5, 0.85, "N", ha="center", va="bottom", fontsize=26)
    ax_compass.text(0.5, 0.15, "S", ha="center", va="top", fontsize=26)
    ax_compass.text(0.15, 0.5, "W", ha="right", va="center", fontsize=26)
    ax_compass.text(0.85, 0.5, "E", ha="left", va="center", fontsize=26)


# Positions the compass rose below the Brazil map, centered.
context_bbox = gs_map_layout[0].get_position(fig)
pos_x = (context_bbox.x0 + context_bbox.x1) / 2 - 0.05
pos_y = context_bbox.y0
add_compass(ax_context, pos_x, pos_y, size=0.06)


# --- 7. EXTERNAL LEGEND IN THREE COLUMNS ---
def create_legend(ax, handles, title):
    """Creates a legend for the specified axis.

    Args:
        ax (matplotlib.axes.Axes): Axis where the legend will be plotted.
        handles (list): List of legend elements (patches or lines).
        title (str): Legend title.

    Returns:
        matplotlib.legend.Legend: Created legend object.
    """
    legend = ax.legend(
        handles=handles,
        title=title,
        alignment="left",
        loc="upper left",
        fontsize=32,
        title_fontsize=34,
        frameon=False,
        handleheight=1.5,
        labelspacing=0.8,
    )
    legend.get_title().set_weight("bold")
    return legend


# Creates an external legend divided into three columns for climate zones.
gs_legend_layout = fig.add_gridspec(
    1,
    3,
    left=0.03,
    right=0.97,
    bottom=0.05,
    top=0.30,
    width_ratios=[0.4, 0.5, 0.7],
    wspace=0.1,
)

# Adds a black border around the external legend.
legend_border = mpatches.Rectangle(
    (0.03, 0.05),
    0.94,
    0.25,
    linewidth=2,
    edgecolor="black",
    facecolor="none",
    transform=fig.transFigure,
    zorder=0,
)
fig.add_artist(legend_border)

# Creates axes for the three legend columns and disables their visual elements.
ax_leg1 = fig.add_subplot(gs_legend_layout[0, 0])
ax_leg1.axis("off")
ax_leg2 = fig.add_subplot(gs_legend_layout[0, 1])
ax_leg2.axis("off")
ax_leg3 = fig.add_subplot(gs_legend_layout[0, 2])
ax_leg3.axis("off")

# Defines legend entries for climate zones (column 1).
zonas_handles = [
    mpatches.Patch(
        color=get_color(
            "Equatorial, quente - média > 18° C em todos os meses, super-úmido sem seca"
        ),
        label="Equatorial",
    ),
    mpatches.Patch(
        color=get_color(
            "Temperado, mesotérmico brando - média entre 10 e 15° C, super-úmido sem seca"
        ),
        label="Temperate",
    ),
    mpatches.Patch(
        color=get_color(
            "Tropical Brasil Central, quente - média > 18° C em todos os meses, semi-árido 7 a 8 meses secos"
        ),
        label="Tropical Central Brazil",
    ),
    mpatches.Patch(
        color=get_color(
            "Tropical Nordeste Oriental, quente - média > 18° C em todos os meses, semi-árido 9 a 10 meses secos"
        ),
        label="Tropical Northeastern Brazil",
    ),
    mpatches.Patch(
        color=get_color(
            "Tropical Zona Equatorial, quente - média > 18° C em todos os meses, semi-árido 11 meses secos"
        ),
        label="Tropical Equatorial Zone",
    ),
]
legend1 = create_legend(ax_leg1, zonas_handles, "Climate Zones")

# Defines legend entries for temperature and humidity (column 2).
temp_umid_handles_col2 = [
    mpatches.Patch(color="#6A339A", label="hot, super-humid no dry season"),
    mpatches.Patch(color="#A378B9", label="hot, super-humid with subseason"),
    mpatches.Patch(color="#D1AAD1", label="hot, humid 1 to 2 dry months"),
    mpatches.Patch(color="#E6D4E6", label="hot, humid 3 dry months"),
    mpatches.Patch(color="#F2EFF2", label="hot, semi-humid 4 to 5 dry months"),
    mpatches.Patch(color="#FFFFBE", label="hot, semi-arid 6 dry months"),
    mpatches.Patch(color="#FFFF00", label="hot, semi-arid 7 to 8 dry months"),
]
legend2 = create_legend(
    ax_leg2, temp_umid_handles_col2, "Temperature and Humidity"
)

# Defines legend entries for temperature and humidity (column 3).
temp_umid_handles_col3 = [
    mpatches.Patch(color="#F7941D", label="hot, semi-arid 9 to 10 dry months"),
    mpatches.Patch(color="#ED1C24", label="hot, semi-arid 11 dry months"),
    mpatches.Patch(color="#8BC53F", label="subhot, humid 1 to 2 dry months"),
    mpatches.Patch(color="#B5D69C", label="subhot, humid 3 dry months"),
    mpatches.Patch(
        color="#D9EAD3", label="subhot, semi-humid 4 to 5 dry months"
    ),
    mpatches.Patch(color="#EFF6E9", label="subhot, semi-arid 6 dry months"),
    mpatches.Patch(
        color="#E6F5FB", label="mild mesothermal, semi-humid 4 to 5 months"
    ),
]
legend3 = create_legend(
    ax_leg3, temp_umid_handles_col3, "Temperature and Humidity"
)

# --- 8. SAVE THE FINAL FIGURE ---
# Saves the generated map as a PNG with high resolution.
print("Plotting completed. Saving the file...")
plt.savefig(OUTPUT_MAP_PATH, dpi=300, bbox_inches="tight", pad_inches=0.1)
print(f"\nAdjusted map saved as '{OUTPUT_MAP_PATH}'!")
