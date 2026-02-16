import sys
import os
from map_poster.theme_management import list_themes, get_available_themes
import zipfile
import urllib.request


def resolve_layer_order(layers):
    """Return layer names in a fetch-safe order.

    Layers can depend on data produced by other layers (for example, the
    ``ocean`` layer uses ``coastline`` geometries as an input mask). This
    helper keeps those dependencies in the right order while preserving the
    relative order of all other layers from the input mapping.
    """
    if not layers:
        return []

    ordered = list(layers.keys())

    # Ensure dependent layers are fetched after their prerequisites.
    dependency_pairs = [
        ("ocean", "coastline"),
    ]

    for layer, prerequisite in dependency_pairs:
        if layer not in ordered or prerequisite not in ordered:
            continue
        if ordered.index(prerequisite) > ordered.index(layer):
            ordered.remove(prerequisite)
            ordered.insert(ordered.index(layer), prerequisite)

    return ordered


def print_examples():
    """Print usage examples."""
    print("""
City Map Poster Generator
=========================

Usage:
  python create_map_poster.py --city <city> --country <country> [options]

Examples:
  # Iconic grid patterns
  python create_map_poster.py -c "New York" -C "USA" -t noir -d 12000           # Manhattan grid
  python create_map_poster.py -c "Barcelona" -C "Spain" -t warm_beige -d 8000   # Eixample district grid

  # Waterfront & canals
  python create_map_poster.py -c "Venice" -C "Italy" -t blueprint -d 4000       # Canal network
  python create_map_poster.py -c "Amsterdam" -C "Netherlands" -t ocean -d 6000  # Concentric canals
  python create_map_poster.py -c "Dubai" -C "UAE" -t midnight_blue -d 15000     # Palm & coastline

  # Radial patterns
  python create_map_poster.py -c "Paris" -C "France" -t pastel_dream -d 10000   # Haussmann boulevards
  python create_map_poster.py -c "Moscow" -C "Russia" -t noir -d 12000          # Ring roads

  # Organic old cities
  python create_map_poster.py -c "Tokyo" -C "Japan" -t japanese_ink -d 15000    # Dense organic streets
  python create_map_poster.py -c "Marrakech" -C "Morocco" -t terracotta -d 5000 # Medina maze
  python create_map_poster.py -c "Rome" -C "Italy" -t warm_beige -d 8000        # Ancient street layout

  # Coastal cities
  python create_map_poster.py -c "San Francisco" -C "USA" -t sunset -d 10000    # Peninsula grid
  python create_map_poster.py -c "Sydney" -C "Australia" -t ocean -d 12000      # Harbor city
  python create_map_poster.py -c "Mumbai" -C "India" -t contrast_zones -d 18000 # Coastal peninsula

  # River cities
  python create_map_poster.py -c "London" -C "UK" -t noir -d 15000              # Thames curves
  python create_map_poster.py -c "Budapest" -C "Hungary" -t copper_patina -d 8000  # Danube split

  # List themes
  python create_map_poster.py --list-themes

Options:
  --city, -c        City name (required)
  --country, -C     Country name (required)
  --country-label   Override country text displayed on poster
  --theme, -t       Theme name (default: terracotta)
  --all-themes      Generate posters for all themes
  --distance, -d    Map radius in meters (default: 18000)
  --list-themes     List all available themes

Distance guide:
  4000-6000m   Small/dense cities (Venice, Amsterdam old center)
  8000-12000m  Medium cities, focused downtown (Paris, Barcelona)
  15000-20000m Large metros, full city view (Tokyo, Mumbai)

Available themes can be found in the 'themes/' directory.
Generated posters are saved to 'posters/' directory.
""")

def resolve_cli_input(args):
    # If no arguments provided, show examples
    if len(sys.argv) == 1:
        print_examples()
        sys.exit(0)
    
    # List themes if requested
    if args.list_themes:
        list_themes()
        sys.exit(0)
    
    # Validate required arguments
    if not args.city or not args.country:
        print("Error: --city and --country are required.\n")
        print_examples()
        sys.exit(1)
    
    available_themes = get_available_themes()
    if not available_themes:
        print("No themes found in 'themes/' directory.")
        os.sys.exit(1)

    if args.all_themes:
        return available_themes
    
    if args.theme not in available_themes:
        print(f"Error: Theme '{args.theme}' not found.")
        print(f"Available themes: {', '.join(available_themes)}")
        os.sys.exit(1)

    return [args.theme]

WATER_URL = "https://osmdata.openstreetmap.de/download/water-polygons-split-4326.zip"

def ensure_water_polygons(data_dir):
    shp_path = os.path.join(data_dir, "water_polygons.shp")

    if os.path.exists(shp_path):
        return shp_path

    print("Water polygons not found — downloading…")

    data_dir.mkdir(exist_ok=True)
    zip_path = os.path.join(data_dir, "water_polygons.zip")

    urllib.request.urlretrieve(WATER_URL, zip_path)

    print("Extracting…")
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            if member.is_dir():
                continue
            
            # remove top-level folder from path
            parts = member.filename.split("/", 1)
            flat_name = parts[1] if len(parts) > 1 else parts[0]
    
            target_path = os.path.join(data_dir, flat_name)
    
            with z.open(member) as src, open(target_path, "wb") as dst:
                dst.write(src.read())
    
    return shp_path
