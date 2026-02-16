"""
Font Management Module
Handles font loading, Google Fonts integration, and caching.
"""

import os
import re
from pathlib import Path
from typing import Optional

try:
    from matplotlib.font_manager import FontProperties
except ModuleNotFoundError:
    FontProperties = None

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT_DIR / "fonts"
FONTS_CACHE_DIR = Path(FONTS_DIR) / "cache"
LOCAL_FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2"}
LOCAL_WEIGHT_TOKENS = {
    "thin",
    "extralight",
    "light",
    "regular",
    "book",
    "medium",
    "semibold",
    "bold",
    "extrabold",
    "black",
    "italic",
    "oblique",
}


def _require_font_properties() -> None:
    if FontProperties is None:
        raise ModuleNotFoundError(
            "No module named 'matplotlib'. Install dependencies with "
            "`pip install -r requirements.txt`."
        )


def _infer_family_from_filename(filename: str) -> str:
    base_name = Path(filename).stem
    parts = re.split(r"[-_ ]+", base_name)
    if parts and parts[-1].lower() in LOCAL_WEIGHT_TOKENS:
        parts = parts[:-1]
    family = " ".join(filter(None, parts)).strip()
    return family or base_name


def _collect_local_fonts() -> dict[str, list[Path]]:
    families: dict[str, list[Path]] = {}
    if not FONTS_DIR.exists():
        return families
    for path in FONTS_DIR.iterdir():
        if path.is_dir():
            continue
        if path.suffix.lower() not in LOCAL_FONT_EXTENSIONS:
            continue
        family = _infer_family_from_filename(path.name)
        families.setdefault(family, []).append(path)
    return families


def list_local_font_families() -> list[str]:
    families = _collect_local_fonts()
    return sorted(families.keys(), key=str.casefold)


def _build_font_weight_map(font_files: list[Path]) -> Optional[dict]:
    weight_map: dict[str, Path] = {}
    for path in font_files:
        name = path.stem.lower()
        if "bold" in name:
            weight_map.setdefault("bold", path)
        elif "light" in name:
            weight_map.setdefault("light", path)
        elif "regular" in name or "book" in name:
            weight_map.setdefault("regular", path)
        else:
            weight_map.setdefault("regular", path)

    if not weight_map:
        return None
    if "regular" not in weight_map:
        weight_map["regular"] = next(iter(weight_map.values()))
    if "bold" not in weight_map:
        weight_map["bold"] = weight_map["regular"]
    if "light" not in weight_map:
        weight_map["light"] = weight_map["regular"]
    return {key: str(path) for key, path in weight_map.items()}


def _get_local_font_set(font_family: str) -> Optional[dict]:
    if not font_family:
        return None
    family_lookup = font_family.strip().lower()
    families = _collect_local_fonts()
    for family_name, font_files in families.items():
        if family_name.lower() == family_lookup:
            return _build_font_weight_map(font_files)
    return None

def download_google_font(font_family: str, weights: list = None) -> Optional[dict]:
    """
    Download a font family from Google Fonts and cache it locally.
    Returns dict with font paths for different weights, or None if download fails.

    :param font_family: Google Fonts family name (e.g., 'Noto Sans JP', 'Open Sans')
    :param weights: List of font weights to download (300=light, 400=regular, 700=bold)
    :return: Dict with 'light', 'regular', 'bold' keys mapping to font file paths
    """
    if weights is None:
        weights = [300, 400, 700]

    # Create fonts cache directory
    FONTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Normalize font family name for file paths
    font_name_safe = font_family.replace(" ", "_").lower()

    font_files = {}

    try:
        # Google Fonts API endpoint - request all weights at once
        weights_str = ";".join(map(str, weights))
        api_url = "https://fonts.googleapis.com/css2"

        # Use requests library for cleaner HTTP handling
        params = {"family": f"{font_family}:wght@{weights_str}"}
        headers = {
            "User-Agent": "Mozilla/5.0"  # Get .woff2 files (better compression)
        }

        # Fetch CSS file
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        css_content = response.text

        # Parse CSS to extract weight-specific URLs
        # Google Fonts CSS has @font-face blocks with font-weight and src: url()
        weight_url_map = {}

        # Split CSS into font-face blocks
        font_face_blocks = re.split(r"@font-face\s*\{", css_content)

        for block in font_face_blocks[1:]:  # Skip first empty split
            # Extract font-weight
            weight_match = re.search(r"font-weight:\s*(\d+)", block)
            if not weight_match:
                continue

            weight = int(weight_match.group(1))

            # Extract URL (prefer woff2, fallback to ttf)
            url_match = re.search(r"url\((https://[^)]+\.(woff2|ttf))\)", block)
            if url_match:
                weight_url_map[weight] = url_match.group(1)

        # Map weights to our keys
        weight_map = {300: "light", 400: "regular", 700: "bold"}

        # Download each weight
        for weight in weights:
            weight_key = weight_map.get(weight, "regular")

            # Find URL for this weight
            weight_url = weight_url_map.get(weight)

            # If exact weight not found, try to find closest
            if not weight_url and weight_url_map:
                # Find closest weight
                closest_weight = min(
                    weight_url_map.keys(), key=lambda x: abs(x - weight)
                )
                weight_url = weight_url_map[closest_weight]
                print(
                    f"  Using weight {closest_weight} for {weight_key} (requested {weight} not available)"
                )

            if weight_url:
                # Determine file extension
                file_ext = "woff2" if weight_url.endswith(".woff2") else "ttf"

                # Download font file
                font_filename = f"{font_name_safe}_{weight_key}.{file_ext}"
                font_path = FONTS_CACHE_DIR / font_filename

                if not font_path.exists():
                    print(f"  Downloading {font_family} {weight_key} ({weight})...")
                    try:
                        font_response = requests.get(weight_url, timeout=10)
                        font_response.raise_for_status()
                        font_path.write_bytes(font_response.content)
                    except Exception as e:
                        print(f"  ⚠ Failed to download {weight_key}: {e}")
                        continue
                else:
                    print(f"  Using cached {font_family} {weight_key}")

                font_files[weight_key] = str(font_path)

        # Ensure we have at least regular weight
        if "regular" not in font_files and font_files:
            # Use first available as regular
            font_files["regular"] = list(font_files.values())[0]
            print(f"  Using {list(font_files.keys())[0]} weight as regular")

        # If we don't have all three weights, duplicate available ones
        if "bold" not in font_files and "regular" in font_files:
            font_files["bold"] = font_files["regular"]
            print("  Using regular weight as bold")
        if "light" not in font_files and "regular" in font_files:
            font_files["light"] = font_files["regular"]
            print("  Using regular weight as light")

        return font_files if font_files else None

    except Exception as e:
        print(f"⚠ Error downloading Google Font '{font_family}': {e}")
        return None


def load_fonts(font_family: Optional[str] = None) -> Optional[dict]:
    """
    Load fonts from local directory or download from Google Fonts.
    Returns dict with font paths for different weights.

    :param font_family: Google Fonts family name (e.g., 'Noto Sans JP', 'Open Sans').
                       If None, uses local Roboto fonts.
    :return: Dict with 'bold', 'regular', 'light' keys mapping to font file paths,
             or None if all loading methods fail
    """
    if font_family:
        local_fonts = _get_local_font_set(font_family)
        if local_fonts:
            print(f"Using local font family: {font_family}")
            return local_fonts

    # If custom font family specified, try to download from Google Fonts
    if font_family and font_family.lower() != "roboto":
        print(f"Loading Google Font: {font_family}")
        fonts = download_google_font(font_family)
        if fonts:
            print(f"✓ Font '{font_family}' loaded successfully")
            return fonts

        print(f"⚠ Failed to load '{font_family}', falling back to local Roboto")

    # Default: Load local Roboto fonts
    fonts = {
        "bold": os.path.join(FONTS_DIR, "Roboto-Bold.ttf"),
        "regular": os.path.join(FONTS_DIR, "Roboto-Regular.ttf"),
        "light": os.path.join(FONTS_DIR, "Roboto-Light.ttf"),
    }

    # Verify fonts exist
    for _weight, path in fonts.items():
        if not os.path.exists(path):
            print(f"⚠ Font not found: {path}")
            return None

    return fonts

def is_latin_script(text):
    """
    Check if text is primarily Latin script.
    Used to determine if letter-spacing should be applied to city names.

    :param text: Text to analyze
    :return: True if text is primarily Latin script, False otherwise
    """
    if not text:
        return True

    latin_count = 0
    total_alpha = 0

    for char in text:
        if char.isalpha():
            total_alpha += 1
            # Latin Unicode ranges:
            # - Basic Latin: U+0000 to U+007F
            # - Latin-1 Supplement: U+0080 to U+00FF
            # - Latin Extended-A: U+0100 to U+017F
            # - Latin Extended-B: U+0180 to U+024F
            if ord(char) < 0x250:
                latin_count += 1

    # If no alphabetic characters, default to Latin (numbers, symbols, etc.)
    if total_alpha == 0:
        return True

    # Consider it Latin if >80% of alphabetic characters are Latin
    return (latin_count / total_alpha) > 0.8


def _safe_float(value, fallback):
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _decode_unicode_escapes(text: str) -> str:
    if not isinstance(text, str):
        return text
    def replace_match(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    text = re.sub(r"\\u([0-9a-fA-F]{4})", replace_match, text)
    text = re.sub(r"\\U([0-9a-fA-F]{8})", replace_match, text)
    return text


def _parse_pos(value, default):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (_safe_float(value[0], default[0]), _safe_float(value[1], default[1]))
    if isinstance(value, dict):
        return (
            _safe_float(value.get("x"), default[0]),
            _safe_float(value.get("y"), default[1]),
        )
    return default


def add_text(
    scale_factor,
    display_city,
    display_country,
    point,
    ax,
    THEME,
    zorder=11,
    fonts=None,
    text_options=None,
):
    _require_font_properties()
    text_options = text_options or {}
    display_city = _decode_unicode_escapes(display_city)
    display_country = _decode_unicode_escapes(display_country)
    # Base font sizes (at 12 inches width)
    base_main = _safe_float(text_options.get("main_size"), 60)
    base_sub = _safe_float(text_options.get("sub_size"), 22)
    base_coords = _safe_float(text_options.get("coords_size"), 14)

    font_family = text_options.get("font_family")
    FONTS = load_fonts(font_family)

    active_fonts = fonts or FONTS
    if active_fonts:
        # font_main is calculated dynamically later based on length
        font_sub = FontProperties(fname=active_fonts["light"], size=base_sub * scale_factor)
        font_coords = FontProperties(fname=active_fonts["regular"], size=base_coords * scale_factor)
    else:
        # Fallback to system fonts
        font_sub = FontProperties(family="monospace", weight="normal", size=base_sub * scale_factor)
        font_coords = FontProperties(family="monospace", size=base_coords * scale_factor)

    # Format city name based on script type
    # Latin scripts: apply uppercase and letter spacing for aesthetic
    # Non-Latin scripts (CJK, Thai, Arabic, etc.): no spacing, preserve case structure
    if is_latin_script(display_city):
        # Latin script: uppercase with letter spacing (e.g., "P  A  R  I  S")
        spaced_city = "  ".join(list(display_city.upper()))
    else:
        # Non-Latin script: no spacing, no forced uppercase
        # For scripts like Arabic, Thai, Japanese, etc.
        spaced_city = display_city

    # Dynamically adjust font size based on city name length to prevent truncation
    # We use the already scaled "main" font size as the starting point.
    base_adjusted_main = base_main * scale_factor
    city_char_count = len(display_city)

    # Heuristic: If length is > 10, start reducing.
    if city_char_count > 10:
        length_factor = 10 / city_char_count
        adjusted_font_size = max(base_adjusted_main * length_factor, 10 * scale_factor) 
    else:
        adjusted_font_size = base_adjusted_main
    
    if active_fonts:
        font_main_adjusted = FontProperties(fname=active_fonts["bold"], size=adjusted_font_size)
    else:
        font_main_adjusted = FontProperties(family='monospace', weight='bold', size=adjusted_font_size)

    # Format coordinates
    lat, lon = point
    coords = f"{lat:.4f}° N / {lon:.4f}° E" if lat >= 0 else f"{abs(lat):.4f}° S / {lon:.4f}° E"
    if lon < 0:
        coords = coords.replace("E", "W")

    show_city = text_options.get("show_city", True)
    show_country = text_options.get("show_country", True)
    show_coords = text_options.get("show_coords", True)
    show_line = text_options.get("show_line", True)

    city_x, city_y = _parse_pos(text_options.get("city_pos"), (0.5, 0.14))
    country_x, country_y = _parse_pos(text_options.get("country_pos"), (0.5, 0.10))
    coords_x, coords_y = _parse_pos(text_options.get("coords_pos"), (0.5, 0.07))
    line_x_start, line_x_end = _parse_pos(text_options.get("line_x"), (0.4, 0.6))
    line_y = _safe_float(text_options.get("line_y"), 0.125)

    # --- ADD CITY,COUNTRY and COORDINATES ---
    if show_city:
        ax.text(city_x, city_y, spaced_city, transform=ax.transAxes, color=THEME, ha='center', fontproperties=font_main_adjusted, zorder=zorder)
    if show_country:
        ax.text(country_x, country_y, display_country.upper(), transform=ax.transAxes, color=THEME, ha="center", fontproperties=font_sub, zorder=zorder)
    if show_coords:
        ax.text(coords_x, coords_y, coords, transform=ax.transAxes, color=THEME, alpha=0.7, ha='center', fontproperties=font_coords, zorder=zorder)
    # --- LINE SEPARATOR ---
    if show_line and (show_city or show_country or show_coords):
        ax.plot([line_x_start, line_x_end], [line_y, line_y], transform=ax.transAxes, color=THEME, linewidth=1 * scale_factor, zorder=zorder)
    
def add_attribution(ax, THEME, zorder=11, text_options=None):
    # --- ATTRIBUTION (bottom right) ---
    _require_font_properties()
    text_options = text_options or {}
    if not text_options.get("show_attribution", True):
        return
    font_family = text_options.get("font_family")
    FONTS = load_fonts(font_family)
    base_attr = _safe_float(text_options.get("attr_size"), 8)
    font_attr = FontProperties(size=base_attr, **({"fname": FONTS["light"]} if FONTS else {"family": "monospace"}))
    attr_x, attr_y = _parse_pos(text_options.get("attr_pos"), (0.98, 0.02))
    ax.text(attr_x, attr_y, "© OpenStreetMap contributors", transform=ax.transAxes, color=THEME, alpha=0.5, ha="right", va="bottom", fontproperties=font_attr, zorder=zorder)
