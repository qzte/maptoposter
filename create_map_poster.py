import osmnx as ox
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import os
import sys
from datetime import datetime
import argparse
import xml.etree.ElementTree as ET
from shapely.geometry import Point
from tqdm import tqdm
import map_poster.cli
from map_poster.font_management import add_text, add_attribution
from map_poster.theme_management import load_theme
from map_poster.fetch import fetch_features, fetch_graph, fetch_ocean_polygons, get_coordinates, convert_linewidth_to_poly
try:
    from lat_lon_parser import parse
except ModuleNotFoundError:
    from map_poster.coordinates import parse_coordinate as parse
import geopandas as gpd
import networkx as nx
import toml
from matplotlib.path import Path as MplPath
from matplotlib.transforms import Affine2D
try:
    from svgpath2mpl import parse_path
except ModuleNotFoundError:
    parse_path = None

_SVG_MARKER_IMPORT_WARNING_SHOWN = False

POSTERS_DIR = "posters"
THEME = dict[str, str]()

CONFIG_FILE = "poster_config.toml"
config = toml.load(CONFIG_FILE)
# Transform flattened 'tags_*' into nested 'tags' dict
for layer_name, layer_conf in config.get("layers", {}).items():
    tags = {}
    for key, value in list(layer_conf.items()):  # list() to allow modification during iteration
        if key.startswith("tags_") and value is not None:
            tag_key = key[5:]  # remove 'tags_' prefix
            tags[tag_key] = value
            del layer_conf[key]  # remove flattened key
    if tags:
        layer_conf["tags"] = tags


LAYERS = config["layers"]
ROAD_STYLES = config["road_styles"]

def generate_output_filename(city, country, theme_name, output_format):
    """
    Generate unique output filename with city, theme, and datetime.
    """
    if not os.path.exists(os.path.join(POSTERS_DIR, country, city)):
        os.makedirs(os.path.join(POSTERS_DIR, country, city))
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    city_slug = city.lower().replace(' ', '_')
    ext = output_format.lower()
    filename = f"{city_slug}_{theme_name}_{timestamp}.{ext}"
    return os.path.join(POSTERS_DIR, country, city, filename)


def create_gradient_fade(ax, color, location='bottom', zorder=10, fade_fraction=0.25):
    """
    Creates a fade effect on a specified side of the map:
    'bottom', 'top', 'left', or 'right'.

    fade_fraction: fraction of axis to apply the fade (default 0.25)
    """
    rgb = mcolors.to_rgb(color)

    # Create RGBA colormap: alpha goes from 1->0 or 0->1 depending on direction
    alphas = np.linspace(1, 0, 256) if location in ['bottom', 'left'] else np.linspace(0, 1, 256)
    my_colors = np.zeros((256, 4))
    my_colors[:, :3] = rgb
    my_colors[:, 3] = alphas
    cmap = mcolors.ListedColormap(my_colors)

    # Get axis limits
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    dx = x1 - x0
    dy = y1 - y0

    # Determine extent and gradient orientation
    if location in ['bottom', 'top']:
        gradient = np.linspace(0, 1, 256).reshape(-1, 1)
        if location == 'bottom':
            extent = [x0, x1, y0, y0 + fade_fraction * dy]
        else:  # top
            extent = [x0, x1, y1 - fade_fraction * dy, y1]
    else:  # left or right
        gradient = np.linspace(0, 1, 256).reshape(1, -1)
        if location == 'left':
            extent = [x0, x0 + fade_fraction * dx, y0, y1]
        else:  # right
            extent = [x1 - fade_fraction * dx, x1, y0, y1]

    ax.imshow(gradient, extent=extent, aspect='auto', cmap=cmap, zorder=zorder, origin='lower')

    
def get_crop_limits(G_proj, center_lat_lon, fig, dist):
    """
    Crop inward to preserve aspect ratio while guaranteeing
    full coverage of the requested radius.
    """
    lat, lon = center_lat_lon

    # Project center point into graph CRS
    center = (ox.projection.project_geometry(Point(lon, lat), crs="EPSG:4326", to_crs=G_proj.graph["crs"])[0])
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

    return ((center_x - half_x, center_x + half_x),(center_y - half_y, center_y + half_y))

def rotate_geometry(gdf, angle, origin):
    """Clockwise rotation"""
    if angle == 0: return gdf
    gdf = gdf.copy()
    gdf["geometry"] = gdf.rotate(-angle, origin=origin)
    return gdf

def calculate_line_scaling(crop_xlim, crop_ylim, width, dpi, px_per_m_ref):
    # --- Calculate linewidth scale factor ---
    # based on reference px per m, based on reference width, DPI and FOV (reference 17.067 inches)
    # This ensures linewidth scaling when changing picture dimensions
    # Reference poster (what you consider “good” line widths)
    # REF_WIDTH_IN = 17.067 # reference width in inches
    # REF_DPI = 300 # reference dpi
    # REF_FOV_X = 53334.375 # REF FOV based on compensated_dist, not just dist
    # px_per_m_ref = 0.096 # Calculating using above balues:px_per_m_ref = (REF_WIDTH_IN * REF_DPI) / REF_FOV_X

    # Compute effective FOV of current image after cropping
    fov_x = crop_xlim[1] - crop_xlim[0]
    fov_y = crop_ylim[1] - crop_ylim[0]

    # Current image pixels per meter dimension
    px_per_m_cur = (width * dpi) / fov_x

    return px_per_m_cur / px_per_m_ref
    

def _build_svg_marker(svg_path):
    global _SVG_MARKER_IMPORT_WARNING_SHOWN
    if svg_path and parse_path is None and not _SVG_MARKER_IMPORT_WARNING_SHOWN:
        print("[WARN] svgpath2mpl não está instalado; usando marcador circular padrão.")
        _SVG_MARKER_IMPORT_WARNING_SHOWN = True
    if not svg_path or parse_path is None:
        return "o"
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
        ns = {"svg": "http://www.w3.org/2000/svg"}
        node = root.find(".//svg:path", ns)
        if node is None:
            node = root.find(".//path")
        if node is None:
            return "o"
        path_data = node.attrib.get("d")
        if not path_data:
            return "o"
        marker_path = parse_path(path_data)
        bbox = marker_path.get_extents()
        max_side = max(bbox.width, bbox.height)
        if max_side == 0:
            return "o"
        transform = Affine2D().translate(-bbox.x0 - bbox.width / 2, -bbox.y0 - bbox.height / 2).scale(1.0 / max_side)
        return MplPath(marker_path.transformed(transform).vertices, marker_path.codes)
    except Exception:
        return "o"


def create_poster(city, country, point, dist, output_file, output_format, width=12, height=16, dpi=300, px_per_m_ref=0.096, country_label=None, name_label=None, refresh_cache=False, display_city=None, display_country=None, fonts=None, pad_inches=0.05, rotation=0, gradient_sides=['bottom', 'top'], fade_fraction=0.25, road_types=None, enabled_layers=None, text_options=None, poi_options=None):
    print(f"\nGenerating map for {city}, {country}...")

    #value init
    display_city = display_city or name_label or city
    display_country = display_country or country_label or country
    #compensated_dist = dist * (max(height, width) / min(height, width))/4 # To compensate for viewport crop
    # We multiply by 1.5 to provide a safe margin for the diagonals after rotation
    rotation_buffer = 1.5 if rotation != 0 else 1.0
    compensated_dist = dist * (max(height, width) / min(height, width)) / 4 * rotation_buffer

    # 1. Fetch Street Network and layers
    results = {}
    plot_layers = dict(LAYERS)
    selected_layers = set(enabled_layers or [])
    if selected_layers:
        # Normalize known aliases against configured layer keys.
        layer_aliases = {
            "oceans": "ocean",
            "ocean": "oceans",
        }
        normalized_layers = set()
        for layer in selected_layers:
            if layer in LAYERS:
                normalized_layers.add(layer)
                continue
            alias = layer_aliases.get(layer)
            if alias and alias in LAYERS:
                normalized_layers.add(alias)
                continue
            normalized_layers.add(layer)
        selected_layers = normalized_layers

        selected_layers.add("street_network")

        # Include prerequisite layers required by selected layers.
        # Example: ocean polygons require coastline geometries.
        layer_dependencies = {
            "ocean": {"coastline", "coastlines"},
            "oceans": {"coastline", "coastlines"},
        }
        pending = list(selected_layers)
        while pending:
            layer = pending.pop()
            for dependency in layer_dependencies.get(layer, set()):
                if dependency in LAYERS and dependency not in selected_layers:
                    selected_layers.add(dependency)
                    pending.append(dependency)

    with tqdm(total=len(LAYERS), desc="Map data", ncols=80, bar_format='{desc:30.30} {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}') as pbar:
        ordered_layers = map_poster.cli.resolve_layer_order(LAYERS)     #Ensure layers are fetched in a safe order
        for layer_name in ordered_layers:
            if selected_layers and layer_name not in selected_layers:
                pbar.update(1)
                continue
            layer_conf = LAYERS[layer_name]
            pbar.set_description(f"Downloading {layer_name}")
            fetch_func = globals()[layer_conf["fetch_func"]]  # fetch_features / fetch_graph / fetch_ocean_polygons

            # Only fetch_features needs tags + name
            if fetch_func == fetch_features:
                tags = layer_conf.get("tags", {})
                results[layer_name] = fetch_func(point, compensated_dist, refresh_cache, tags=tags, name=layer_name)
            elif fetch_func == fetch_ocean_polygons:
                # some layers like oceans may want dynamic kwargs
                coastline = results.get("coastline")
                if coastline is None or (isinstance(coastline, gpd.GeoDataFrame) and coastline.empty):
                    coastline = results.get("coastlines")
                results[layer_name] = fetch_func(point,compensated_dist,refresh_cache,coastline=coastline)

            else:  # fetch_graph
                results[layer_name] = fetch_func(point, compensated_dist, refresh_cache)

            pbar.update(1)

    G = results["street_network"]
    if G is None: raise RuntimeError("Failed to retrieve street network data.")

    # Handle aeroway runway convertion from line+width to polygons
    aeroway = results.pop("aeroway", None)
    if aeroway is not None and not (isinstance(aeroway, gpd.GeoDataFrame) and aeroway.empty):
        polygons, lines = convert_linewidth_to_poly(aeroway)
        conf = LAYERS.get("aeroway", {})

        for suffix, data in {"aeroway_polygons": polygons, "aeroway_lines": lines,}.items():
            plot_layers[suffix] = {**conf}
            results[suffix] = data

    # 2. Setup Plot
    print("Rendering map...")
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi, facecolor=THEME['bg'])    
    ax.set_facecolor(THEME['bg'])
    ax.set_position((0.0, 0.0, 1.0, 1.0))
    ax.set_axis_off()
    ax.set_aspect('equal', adjustable='box')   

    # Project graph to a metric CRS so distances and aspect are linear (meters)
    G_proj = ox.project_graph(G)
    center_pt = ox.projection.project_geometry(Point(point[1], point[0]), to_crs=G_proj.graph["crs"])[0]

    # Determine cropping limits to maintain the poster aspect ratio
    crop_xlim, crop_ylim = get_crop_limits(G_proj, point, fig, compensated_dist / rotation_buffer)
    ax.set_xlim(crop_xlim)
    ax.set_ylim(crop_ylim) 

    # Line scaling factor to ensure consistant line scale even when changing poster dimensions and dpi
    line_scale_factor = calculate_line_scaling(crop_xlim, crop_ylim, width, dpi, px_per_m_ref)
    
    # 3. Plot Layers
    # --- Layer definitions for plotting ---
    print("Adding layers...")

    # --- Plot all layers in a loop ---
    for layer_name, layer_conf in plot_layers.items():
        if selected_layers and layer_name not in selected_layers:
            continue
        layer_data = results.get(layer_name)
        if layer_data is None or (isinstance(layer_data, gpd.GeoDataFrame) and layer_data.empty) or isinstance(layer_data, nx.MultiDiGraph):
            continue  # skip plotting here; ie roads handled separately
        filtered = layer_data[layer_data.geometry.type.isin(['Polygon','MultiPolygon','LineString','MultiLineString'])]  # Used to filter out points
        if filtered.empty:
            continue

        try:
            projected = ox.projection.project_gdf(filtered)
        except Exception:
            projected = filtered.to_crs(G_proj.graph['crs'])
        projected = rotate_geometry(projected, rotation, center_pt)

        color = THEME.get(layer_conf.get("color_theme_key")) or THEME.get(layer_conf.get("fallback_keys")) or THEME.get("bg")
        lw = layer_conf.get("linewidth", 0)
        z = layer_conf.get("zorder", 1)
        alpha = layer_conf.get("alpha", 1)

        if projected.geometry.type.isin(['Polygon','MultiPolygon']).any():
            projected.plot(ax=ax, facecolor=color, linewidth=lw*line_scale_factor, edgecolor=THEME.get(layer_conf.get("outline",""), "none"), zorder=z, alpha=alpha)
        else:
            projected.plot(ax=ax, color=color, linewidth=lw*line_scale_factor, zorder=z, alpha=alpha)
            ax.collections[-1].set_capstyle("round")
            core_key = f"{layer_conf['color_theme_key']}_core"
            if core_key in THEME:
                projected.plot(ax=ax, color=THEME[core_key], linewidth=0.2*line_scale_factor, zorder=z+0.1, alpha=alpha)
                ax.collections[-1].set_capstyle("round")

    # Roads with hierarchy coloring, width, and order
    print("Applying road hierarchy...")
    edges = ox.graph_to_gdfs(G_proj, nodes=False, edges=True)    # Convert graph edges to GeoDataFrame
    edges = rotate_geometry(edges, rotation, center_pt)

    # Normalize highway values (take first element if list, fallback to 'unclassified')
    edges["highway_norm"] = edges["highway"].apply(lambda h: (h[0] if isinstance(h, list) and h else h) or 'unclassified')

    # Apply styles to edges
    edges["style"]      = edges["highway_norm"].map(lambda h: ROAD_STYLES.get(h, {'order':1,'theme_key':'road_default','width':0.4}))
    edges["draw_order"] = edges["style"].map(lambda s: s["order"])
    edges["width"]      = edges["style"].map(lambda s: s["width"])
    edges["theme_key"]  = edges["style"].map(lambda s: s["theme_key"])
    edges["color"]      = edges["theme_key"].map(lambda k: THEME.get(k, THEME["road_default"]))

    selected_road_types = set(road_types or [])
    if selected_road_types:
        edges = edges[edges["highway_norm"].isin(selected_road_types)]

    # Draw roads per hierarchy level
    for order in sorted(edges["draw_order"].unique()):
        subset = edges[edges["draw_order"] == order]

        # Base pass
        subset.plot(ax=ax,color=subset["color"],linewidth=subset["width"] * line_scale_factor,zorder=5 + order * 0.01)
        ax.collections[-1].set_capstyle("round")

        # Extra core line if defined in THEME
        core_key = f"{subset.iloc[0]['theme_key']}_core"
        if core_key in THEME:
            subset.plot(ax=ax,color=THEME[core_key],linewidth= 0.3 * subset["width"] * line_scale_factor,zorder=5 + order * 0.01 + 0.005, alpha = 0.9) #add core lines in between defined road order
            ax.collections[-1].set_capstyle("round")

    if poi_options and poi_options.get("coords"):
        poi_lat, poi_lon = poi_options["coords"]
        poi_pt = ox.projection.project_geometry(Point(poi_lon, poi_lat), crs="EPSG:4326", to_crs=G_proj.graph["crs"])[0]
        poi_point = gpd.GeoSeries([Point(poi_pt.x, poi_pt.y)], crs=G_proj.graph["crs"])
        poi_point = rotate_geometry(poi_point.to_frame(name="geometry"), rotation, center_pt)
        marker_size = float(poi_options.get("size", 12)) ** 2
        marker_color = poi_options.get("color") or "#e53935"
        marker = _build_svg_marker(poi_options.get("svg_path", ""))
        x = poi_point.geometry.iloc[0].x
        y = poi_point.geometry.iloc[0].y
        ax.scatter(x, y, s=marker_size, c=marker_color, marker=marker, zorder=9, edgecolors="none")

    # 4. Add Gradients
    #gradient_sides = ['bottom', 'top', 'left', 'right']  # choose which sides you want
    if gradient_sides is not None:
        print("Add fading gradients to poster")
        for side in gradient_sides:
            create_gradient_fade(ax, THEME['gradient_color'], location=side, zorder=10, fade_fraction = fade_fraction)
    
    # 5. Typography - use custom fonts if provided, otherwise use default FONTS
    print("Add Text elements")
    # Calculate scale factor based on smaller dimension (reference 12 inches)
    # This ensures text scales properly for both portrait and landscape orientations
    font_scale_factor = min(height, width) / 12.0
    add_text(font_scale_factor, display_city, display_country, point, ax, THEME['text'], zorder=11, fonts=fonts, text_options=text_options)
    add_attribution(ax, THEME['text'], zorder=11, text_options=text_options)
 
    # 6. Save
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
    parser.add_argument("--latitude","-lat",dest="latitude",type=str,help="Override latitude center point")
    parser.add_argument("--longitude","-long",dest="longitude",type=str,help="Override longitude center point")
    parser.add_argument('--country-label', dest='country_label', type=str, help='Override country text displayed on poster')
    parser.add_argument('--theme', '-t', type=str, default='feature_based', help='Theme name (default: feature_based)')
    parser.add_argument('--all-themes', '--All-themes', dest='all_themes', action='store_true', help='Generate posters for all themes')
    parser.add_argument('--distance', '-d', type=int, default=29000, help='Map radius in meters (default: 29000)')
    parser.add_argument('--rotation', '-r', type=float, default=0, help='clockwise rotation of the map (default: 0)')
    parser.add_argument('--width', '-W', type=float, default=12, help='Image width in inches (default: 12)')
    parser.add_argument('--height', '-H', type=float, default=16, help='Image height in inches (default: 16)')
    parser.add_argument('--px_per_m', '-P', type=float, default=0.096, help='Reference px per meter for line width scaling (default: 0.096)')
    parser.add_argument('--gradient-sides', '-gs', type=str, default="bottom,top", help="Comma-separated sides to add gradient on. Options: bottom, top, left, right. Pass 'none' to skip gradients entirely.")
    parser.add_argument('--fade-fraction', '-ff', type=float, default=0.25, help="Fraction of the map covered by gradient fade (default: 0.25)")
    parser.add_argument('--list-themes', action='store_true', help='List all available themes')
    parser.add_argument('--format', '-f', default='png', choices=['png', 'svg', 'pdf'],help='Output format for the poster (default: png)')
    parser.add_argument('--dpi', type=int, default=300, help='DPI value for saving as png (default: 300)')
    parser.add_argument('--pad', type=float, default=0.05, help='add border around image, value in inches (default: 0.05)')
    parser.add_argument('--refresh-cache', '-R', action='store_true', help='Force a refresh of the cached data (default: False)')
    
    args = parser.parse_args()

    themes_to_generate = map_poster.cli.resolve_cli_input(args)
    
    print("=" * 50)
    print("City Map Poster Generator")
    print("=" * 50)
    
    # Get coordinates and generate poster
    try:
        if args.latitude and args.longitude:
            lat = parse(args.latitude)
            lon = parse(args.longitude)
            coords = [lat, lon]
            print(f"✓ Coordinates: {', '.join([str(i) for i in coords])}")
        else:
            coords = get_coordinates(args.city, args.country, args.refresh_cache)

        if args.gradient_sides.lower() == 'none':
            gradient_sides = None
        else:
            gradient_sides = [s.strip() for s in args.gradient_sides.split(',')]

        for theme_name in themes_to_generate:
            THEME = load_theme(theme_name)
            output_file = generate_output_filename(args.city, args.country, theme_name, args.format)
            create_poster(args.city, args.country, coords, args.distance, output_file, args.format, args.width, args.height, dpi=args.dpi, px_per_m_ref=args.px_per_m, country_label=args.country_label, refresh_cache=args.refresh_cache, pad_inches=args.pad, rotation=args.rotation, gradient_sides=gradient_sides, fade_fraction = args.fade_fraction)
        
        print("\n" + "=" * 50)
        print("✓ Poster generation complete!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
