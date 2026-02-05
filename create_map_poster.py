import osmnx as ox
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from tqdm import tqdm
import os
import sys
from datetime import datetime
import argparse
from shapely.geometry import Point
from tqdm import tqdm
import map_poster.cli
from map_poster.font_management import add_text, add_attribution
from map_poster.theme_management import load_theme
from map_poster.fetch import fetch_features, fetch_graph, fetch_ocean_polygons, get_coordinates
from pathlib import Path

POSTERS_DIR = "posters"
WATER_POLY_DIR = Path("cache/water_polygons")

THEME = dict[str, str]()  # Will be loaded later

# OSM Highway Types:
# - Road Hierarchy (low → high): path/track/footway/cycleway → service → residential/living_street/unclassified
#   → tertiary → secondary → primary → trunk → motorway (and *_link variants).
# Typography Positioning:
# - Map typography is added after layers/gradients via add_text/add_attribution with a font scale based on
#   the smaller poster dimension to preserve balance across portrait/landscape outputs.
# Useful OSMnx Patterns:
# - Project graph/GeoDataFrames to a metric CRS before distance-based cropping or linewidth scaling.
# - Use graph_to_gdfs for styling edges and normalize list-like highway tags to a single value.

def generate_output_filename(city, theme_name, output_format):
    """
    Generate unique output filename with city, theme, and datetime.
    """
    if not os.path.exists(os.path.join(POSTERS_DIR, city)):
        os.makedirs(os.path.join(POSTERS_DIR, city))
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    city_slug = city.lower().replace(' ', '_')
    ext = output_format.lower()
    filename = f"{city_slug}_{theme_name}_{timestamp}.{ext}"
    return os.path.join(POSTERS_DIR, city, filename)

def create_gradient_fade(ax, color, location='bottom', zorder=10):
    """
    Creates a fade effect at the top or bottom of the map.
    """
    vals = np.linspace(0, 1, 256).reshape(-1, 1)
    gradient = np.hstack((vals, vals))
    
    rgb = mcolors.to_rgb(color)
    my_colors = np.zeros((256, 4))
    my_colors[:, 0] = rgb[0]
    my_colors[:, 1] = rgb[1]
    my_colors[:, 2] = rgb[2]
    
    if location == 'bottom':
        my_colors[:, 3] = np.linspace(1, 0, 256)
        extent_y_start = 0
        extent_y_end = 0.25
    else:
        my_colors[:, 3] = np.linspace(0, 1, 256)
        extent_y_start = 0.75
        extent_y_end = 1.0

    custom_cmap = mcolors.ListedColormap(my_colors)
    
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    y_range = ylim[1] - ylim[0]
    
    y_bottom = ylim[0] + y_range * extent_y_start
    y_top = ylim[0] + y_range * extent_y_end
    
    ax.imshow(gradient, extent=[xlim[0], xlim[1], y_bottom, y_top], 
              aspect='auto', cmap=custom_cmap, zorder=zorder, origin='lower')
    
def get_crop_limits(G_proj, center_lat_lon, fig, dist):
    """
    Crop inward to preserve aspect ratio while guaranteeing
    full coverage of the requested radius.
    """
    lat, lon = center_lat_lon

    # Project center point into graph CRS
    center = (
        ox.projection.project_geometry(
            Point(lon, lat),
            crs="EPSG:4326",
            to_crs=G_proj.graph["crs"]
        )[0]
    )
    center_x, center_y = center.x, center.y

    fig_width, fig_height = fig.get_size_inches()
    aspect = fig_width / fig_height

    # Start from the *requested* radius
    half_x = dist
    half_y = dist

    # Cut inward to match aspect
    if aspect > 1:  # landscape → reduce height
        half_y = half_x / aspect
    else:           # portrait → reduce width
        half_x = half_y * aspect

    return (
        (center_x - half_x, center_x + half_x),
        (center_y - half_y, center_y + half_y),
    )

def calculate_line_scaling(crop_xlim, crop_ylim, width, dpi):
    # --- Calculate linewidth scale factor ---
    # based on reference px per m, based on reference width, DPI and FOV (reference 17.067 inches)
    # This ensures linewidth scaling when changing picture dimensions
    # Reference poster (what you consider “good” line widths)
    REF_WIDTH_IN = 17.067 # reference width in inches
    REF_DPI = 300 # reference dpi
    REF_FOV_X = 53334.375 # REF FOV based on compensated_dist, not just dist
    px_per_m_ref = 0.096 # Calculating using above balues:px_per_m_ref = (REF_WIDTH_IN * REF_DPI) / REF_FOV_X

    # Compute effective FOV of current image after cropping
    fov_x = crop_xlim[1] - crop_xlim[0]
    fov_y = crop_ylim[1] - crop_ylim[0]

    # Current image pixels per meter dimension
    px_per_m_cur = (width * dpi) / fov_x

    return px_per_m_cur / px_per_m_ref
    

def create_poster(city, country, point, dist, output_file, output_format, width=12, height=16, dpi=300, country_label=None, name_label=None, refresh_cache=False, display_city=None, display_country=None, fonts=None, pad_inches=0.05):
    print(f"\nGenerating map for {city}, {country}...")

    #value init
    display_city = display_city or name_label or city
    display_country = display_country or country_label or country
    compensated_dist = dist * (max(height, width) / min(height, width))/4 # To compensate for viewport crop

    # 1. Fetch Street Network and layers
    # Define layers and their specific tags
    common_args = (point, compensated_dist, refresh_cache)
    layers = [
        ("street network",  fetch_graph, {}),
        ("water",           fetch_features, {"tags": {'natural': ['water', 'bay', 'strait'], 'waterway': ['riverbank', 'dock', 'canal']},"name": 'water'}),
        ("rivers",          fetch_features, {"tags": {'waterway': ['river', 'stream']},"name": 'rivers'}),
        ("coastline",       fetch_features, {"tags": {'natural': 'coastline'},"name": 'coast'}),
        ("oceans",          fetch_ocean_polygons, {"coastline": lambda results: results.get("coastline")}),
        ("forests",         fetch_features, {"tags": {"natural":["wood"],"landuse":["forest","logging"]},"name": "forest"}),
        ("green spaces",    fetch_features, {"tags": {"natural":["grassland"],"landuse":["grass","recreation_ground","religious","village_green","greenery","greenfield","meadow", "vineyard"],"leisure":["park","garden"]},"name": "grass"}),
        ("farmland",        fetch_features, {"tags": {"landuse":["farmland"],"natural":["heath", "scrub"]},"name": "farmland"}),
        ("wetlands",        fetch_features, {"tags": {"natural":["wetland"],"landuse":["salt_pond"]},"name": "wetlands"}),
        ("beaches",         fetch_features, {"tags": {"natural":["beach","sand"]},"name": "beaches"}),
        ("industrial",      fetch_features, {"tags": {"landuse":["industrial","commercial","construction"]},"name": "industrial"}),
        ("residential",     fetch_features, {"tags": {"landuse":["residential"]},"name": "residential"}),
        ("buildings",       fetch_features, {"tags": {"building": True},"name": "buildings"}),
        ("parking",         fetch_features, {"tags": {"amenity":["parking"],"parking":["surface","multi-storey","underground"]},"name": "parking"}),
        ("sports",          fetch_features, {"tags": {"leisure":["stadium","sports_centre","pitch"]},"name": "sports"}),
        ("aerodrome",       fetch_features, {"tags": {"aeroway":["aerodrome"]},"name": "aerodrome"}),
        ("runways",         fetch_features, {"tags": {"aeroway":["runway","taxiway"]},"name": "runways"}),
        ("railways",        fetch_features, {"tags": {"railway": ["rail", "narrow_gauge", "monorail", "light_rail"]},"name": "railways"}),
        ("subtram",         fetch_features, {"tags": {"railway": ["subway", "funicular", "tram"]},"name": "subtram"}),
    ]

    results = {}
    with tqdm(total=len(layers), desc="Map data", ncols=80, bar_format='{desc:30.30} {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}') as pbar:
        for name, func, extra_kwargs in layers:
            pbar.set_description(f"Downloading {name}")
            # Evaluate dynamic kwargs if they are lambdas
            kwargs = {k: v(results) if callable(v) else v for k, v in extra_kwargs.items()}
            results[name] = func(*common_args, **kwargs)
            pbar.update(1)

    G = results["street network"]
    if G is None: raise RuntimeError("Failed to retrieve street network data.")

    water, rivers, oceans = results["water"], results["rivers"], results["oceans"]
    forests = results["forests"]
    grass = results["green spaces"]
    farmland = results["farmland"]
    wetlands = results["wetlands"]
    beaches = results["beaches"]
    industrial = results["industrial"]
    residential = results["residential"]
    buildings = results["buildings"]
    parking = results["parking"]
    sports = results["sports"]
    aerodrome = results["aerodrome"]
    runways = results["runways"]
    railways = results["railways"]
    subtram = results["subtram"]

    # 2. Setup Plot
    print("Rendering map...")
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi, facecolor=THEME['bg'])    
    ax.set_facecolor(THEME['bg'])
    ax.set_position((0.0, 0.0, 1.0, 1.0))
    ax.set_axis_off()
    ax.set_aspect('equal', adjustable='box')   

    # Project graph to a metric CRS so distances and aspect are linear (meters)
    G_proj = ox.project_graph(G)

    # Determine cropping limits to maintain the poster aspect ratio
    crop_xlim, crop_ylim = get_crop_limits(G_proj, point, fig, compensated_dist)
    ax.set_xlim(crop_xlim)
    ax.set_ylim(crop_ylim) 

    # Line scaling factor to ensure consistant line scale even when changing poster dimensions and dpi
    line_scale_factor = calculate_line_scaling(crop_xlim, crop_ylim, width, dpi)
    
    # 3. Plot Layers
    # Layer 1: Polygons (filter to only plot polygon/multipolygon geometries, not points)
    # --- Layer definitions for plotting ---
    print("Adding layers...")
    plot_layers = [
      # (layer_key, layer_data,   allowed_geom_types,                  facecolor / color,                                          linewidth,   zorder)
        ("ocean",      oceans,      ['Polygon','MultiPolygon'],          THEME['water'],                                             None,        0),
        ("water",      water,       ['Polygon','MultiPolygon'],          THEME['water'],                                             None,        2),
        ("river",      rivers,      ['LineString','MultiLineString'],    THEME['water'],                                             2.0,         3),
        ("forest",     forests,     ['Polygon','MultiPolygon'],          THEME.get('forest', THEME.get('parks')),                    None,        1),
        ("grass",      grass,       ['Polygon','MultiPolygon'],          THEME.get('grass', THEME.get('parks')),                     None,        1),
        ("farmland",   farmland,    ['Polygon','MultiPolygon'],          THEME.get('farmland', THEME.get('parks')),                  None,        1),
        ("wetlands",   wetlands,    ['Polygon','MultiPolygon'],          THEME.get('wetlands', THEME.get('parks')),                  None,        1),
        ("beaches",    beaches,     ['Polygon','MultiPolygon'],          THEME.get('beach', THEME.get('parks')),                     None,        1),
        ("industrial", industrial,  ['Polygon','MultiPolygon'],          THEME.get('industrial', THEME.get('parks')),                None,        1),
        ("residential",residential,['Polygon','MultiPolygon'],           THEME.get('residential', THEME.get('parks')),               None,        1),
        ("buildings",  buildings,   ['Polygon','MultiPolygon'],          THEME.get('building', THEME.get('road_default')),           None,        4),
        ("parking",    parking,     ['Polygon','MultiPolygon'],          THEME.get('parking', THEME.get('parks')),                   None,        3.5),
        ("sports",     sports,      ['Polygon','MultiPolygon'],          THEME.get('sports', THEME.get('parks')),                    None,        3.5),
        ("aerodrome",  aerodrome,   ['Polygon','MultiPolygon'],          THEME.get('aerodrome', THEME.get('parks')),                 None,        3),
        ("runway",     runways,     ['LineString','MultiLineString'],    THEME.get('runway', THEME.get('road_primary')),             1.4,         6.1),
        ("railway",    railways,    ['LineString','MultiLineString'],    THEME.get('railway', THEME.get('road_primary')),            1.0,         6.2),
        ("subtram",    subtram,     ['LineString','MultiLineString'],    THEME.get('subtram', THEME.get('road_primary')),            0.8,         6)
    ]

    # --- Plot all layers in a loop ---
    for layer_key, layer_data, geom_types, color, lw, z in plot_layers:
        if layer_data is not None and not layer_data.empty:
            filtered = layer_data[layer_data.geometry.type.isin(geom_types)]
            if not filtered.empty:
                try:
                    projected = ox.projection.project_gdf(filtered)
                except Exception:
                    projected = filtered.to_crs(G_proj.graph['crs'])

                # Plot
                if 'Polygon' in geom_types or 'MultiPolygon' in geom_types:
                    projected.plot(ax=ax, facecolor=color, edgecolor='none', zorder=z)
                else:  # Lines
                    coll = projected.plot(ax=ax, color=color, linewidth=lw*line_scale_factor, zorder=z, alpha=0.7)
                    ax.collections[-1].set_capstyle("round")  # Round end of line
                    core_key = f"{layer_key}_core"
                    if core_key in THEME:
                        # Extra extra core line (good for adding a "glowing effect")
                        coll = projected.plot(ax=ax, color=THEME[core_key], linewidth=0.2*line_scale_factor, zorder=z+0.1, alpha=0.7)
                        ax.collections[-1].set_capstyle("round")  # Round end of line

    # Layer 2: Roads with hierarchy coloring, width, and order
    print("Applying road hierarchy...")
    edges = ox.graph_to_gdfs(G_proj, nodes=False, edges=True)    # Convert graph edges to GeoDataFrame

    # Normalize highway values (take first element if list, fallback to 'unclassified')
    edges["highway_norm"] = edges["highway"].apply(lambda h: (h[0] if isinstance(h, list) and h else h) or 'unclassified')

    # Define a road style library
    ROAD_STYLES = {
        'path':           {'order': 0, 'color': THEME.get("road_track", THEME["road_default"]), 'width': 0.1},
        'track':          {'order': 0, 'color': THEME.get("road_track", THEME["road_default"]), 'width': 0.1},
        'pedestrian':     {'order': 0, 'color': THEME.get("road_track", THEME["road_default"]), 'width': 0.1},
        "footway":        {'order': 0, 'color': THEME.get("road_track", THEME["road_default"]), 'width': 0.1},
        "cycleway":       {'order': 0, 'color': THEME.get("road_track", THEME["road_default"]), 'width': 0.1},
        'service':        {'order': 1, 'color': THEME.get("road_service", THEME["road_default"]), 'width': 0.4},
        'residential':    {'order': 2, 'color': THEME.get("road_residential", THEME["road_default"]), 'width': 0.4},
        'living_street':  {'order': 2, 'color': THEME.get("road_residential", THEME["road_default"]), 'width': 0.4},
        'unclassified':   {'order': 2, 'color': THEME.get("road_residential", THEME["road_default"]), 'width': 0.4},
        'tertiary':       {'order': 3, 'color': THEME.get("road_tertiary", THEME["road_default"]), 'width': 0.6},
        'tertiary_link':  {'order': 3, 'color': THEME.get("road_tertiary", THEME["road_default"]), 'width': 0.6},
        'secondary':      {'order': 4, 'color': THEME.get("road_secondary", THEME["road_default"]), 'width': 0.8},
        'secondary_link': {'order': 4, 'color': THEME.get("road_secondary", THEME["road_default"]), 'width': 0.8},
        'primary':        {'order': 5, 'color': THEME.get("road_primary", THEME["road_default"]), 'width': 1.0},
        'primary_link':   {'order': 5, 'color': THEME.get("road_primary", THEME["road_default"]), 'width': 1.0},
        'trunk':          {'order': 6, 'color': THEME.get("road_primary", THEME["road_default"]), 'width': 1.0},
        'trunk_link':     {'order': 6, 'color': THEME.get("road_primary", THEME["road_default"]), 'width': 1.0},
        'motorway':       {'order': 7, 'color': THEME.get("road_motorway", THEME["road_default"]), 'width': 1.2},
        'motorway_link':  {'order': 7, 'color': THEME.get("road_motorway", THEME["road_default"]), 'width': 1.2},
    }

    # Apply styles to edges
    edges["draw_order"] = edges["highway_norm"].map(lambda h: ROAD_STYLES.get(h, {'order':1})['order'])
    edges["color"]      = edges["highway_norm"].map(lambda h: ROAD_STYLES.get(h, {'color':THEME["road_default"]})['color'])
    edges["width"]      = edges["highway_norm"].map(lambda h: ROAD_STYLES.get(h, {'width':0.4})['width'])

    # Sort by draw order so smaller roads are plotted on top of larger ones
    edges = edges.sort_values("draw_order")
    coll = edges.plot(ax=ax,color=edges["color"],linewidth=edges["width"] * line_scale_factor,zorder=5)   
    ax.collections[-1].set_capstyle("round")  # Round end of line

    # Layer 3: Gradients (Top and Bottom)
    create_gradient_fade(ax, THEME['gradient_color'], location='bottom', zorder=10)
    create_gradient_fade(ax, THEME['gradient_color'], location='top', zorder=10)
    
    # Calculate scale factor based on smaller dimension (reference 12 inches)
    # This ensures text scales properly for both portrait and landscape orientations
    font_scale_factor = min(height, width) / 12.0

    # 4. Typography - use custom fonts if provided, otherwise use default FONTS
    add_text(font_scale_factor, display_city, display_country, point, ax, THEME['text'], zorder=11, fonts=fonts)
    add_attribution(ax, THEME['text'], zorder=11)
 
    # 5. Save
    print(f"Saving to {output_file}...")

    fmt = output_format.lower()
    save_kwargs = dict(facecolor=THEME["bg"], bbox_inches="tight", pad_inches=pad_inches)

    # DPI matters mainly for raster formats
    if fmt == "png":
        save_kwargs["dpi"] = dpi

    plt.savefig(output_file, format=fmt, **save_kwargs)

    plt.close()
    print(f"✓ Done! Poster saved as {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate beautiful map posters for any city",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python create_map_poster.py --city "New York" --country "USA"
  python create_map_poster.py --city Tokyo --country Japan --theme midnight_blue
  python create_map_poster.py --city Paris --country France --theme noir --distance 15000
  python create_map_poster.py --list-themes
        """
    )
    
    parser.add_argument('--city', '-c', type=str, help='City name')
    parser.add_argument('--country', '-C', type=str, help='Country name')
    parser.add_argument('--country-label', dest='country_label', type=str, help='Override country text displayed on poster')
    parser.add_argument('--theme', '-t', type=str, default='feature_based', help='Theme name (default: feature_based)')
    parser.add_argument('--all-themes', '--All-themes', dest='all_themes', action='store_true', help='Generate posters for all themes')
    parser.add_argument('--distance', '-d', type=int, default=29000, help='Map radius in meters (default: 29000)')
    parser.add_argument('--width', '-W', type=float, default=12, help='Image width in inches (default: 12)')
    parser.add_argument('--height', '-H', type=float, default=16, help='Image height in inches (default: 16)')
    parser.add_argument('--list-themes', action='store_true', help='List all available themes')
    parser.add_argument('--format', '-f', default='png', choices=['png', 'svg', 'pdf'],help='Output format for the poster (default: png)')
    parser.add_argument('--dpi', type=int, default=300, help='DPI value for saving as png (default: 300)')
    parser.add_argument('--refresh-cache', '-R', action='store_true', help='Force a refresh of the cached data (default: False)')
    
    args = parser.parse_args()

    themes_to_generate = map_poster.cli.resolve_cli_input(args)
    
    print("=" * 50)
    print("City Map Poster Generator")
    print("=" * 50)
    
    # Get coordinates and generate poster
    try:
        coords = get_coordinates(args.city, args.country, args.refresh_cache)
        for theme_name in themes_to_generate:
            THEME = load_theme(theme_name)
            output_file = generate_output_filename(args.city, theme_name, args.format)
            create_poster(args.city, args.country, coords, args.distance, output_file, args.format, args.width, args.height, dpi=args.dpi, country_label=args.country_label, refresh_cache=args.refresh_cache)
        
        print("\n" + "=" * 50)
        print("✓ Poster generation complete!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
