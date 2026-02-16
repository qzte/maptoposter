import inspect
import json
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    import create_map_poster as poster
    POSTER_IMPORT_ERROR: ModuleNotFoundError | None = None
except ModuleNotFoundError as exc:
    poster = None
    POSTER_IMPORT_ERROR = exc

from lat_lon_parser import parse
from map_poster.font_management import list_local_font_families
from map_poster.theme_management import get_available_themes, load_theme


class PosterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("City Map Poster Generator")
        self.root.geometry("860x820")
        self.root.minsize(780, 720)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self._configure_style()

        self.theme_names = get_available_themes()
        if not self.theme_names:
            messagebox.showerror("Erro", "Nenhum tema encontrado em themes/.")
            self.root.destroy()
            return
        self.local_font_families = list_local_font_families()

        self._build_ui()

    def _configure_style(self) -> None:
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.colors = {
            "bg": "#eaf2fb",
            "card": "#f7fbff",
            "border": "#c7dbf2",
            "text": "#0f2c4c",
            "muted": "#3f5f7f",
            "accent": "#1e88e5",
            "accent_dark": "#1565c0",
            "accent_light": "#bbdefb",
        }

        self.root.configure(bg=self.colors["bg"])
        self.style.configure(
            ".",
            background=self.colors["bg"],
            foreground=self.colors["text"],
            font=("Segoe UI", 10),
        )
        self.style.configure("TFrame", background=self.colors["bg"])
        self.style.configure("Card.TFrame", background=self.colors["card"])
        self.style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"])
        self.style.configure(
            "TLabelframe",
            background=self.colors["card"],
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            relief="solid",
        )
        self.style.configure("TLabelframe.Label", background=self.colors["card"], foreground=self.colors["muted"])
        self.style.configure(
            "TEntry",
            fieldbackground="white",
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            lightcolor=self.colors["border"],
            darkcolor=self.colors["border"],
            padding=6,
        )
        self.style.configure(
            "Text.TEntry",
            fieldbackground="white",
            foreground=self.colors["text"],
            bordercolor=self.colors["accent_light"],
            lightcolor=self.colors["accent_light"],
            darkcolor=self.colors["accent_light"],
            padding=8,
        )
        self.style.configure(
            "TCombobox",
            fieldbackground="white",
            foreground=self.colors["text"],
            bordercolor=self.colors["border"],
            padding=6,
        )
        self.style.configure(
            "TButton",
            background=self.colors["accent"],
            foreground="white",
            padding=(14, 8),
            borderwidth=0,
        )
        self.style.map(
            "TButton",
            background=[
                ("active", self.colors["accent_dark"]),
                ("pressed", self.colors["accent_dark"]),
            ],
            foreground=[("disabled", "#d7e5f5")],
        )
        self.style.configure(
            "Secondary.TButton",
            background=self.colors["accent_light"],
            foreground=self.colors["accent_dark"],
            padding=(12, 6),
        )
        self.style.map(
            "Secondary.TButton",
            background=[("active", "#a9cff7"), ("pressed", "#90c2f3")],
            foreground=[("disabled", "#8fb7e5")],
        )
        self.style.configure("TCheckbutton", background=self.colors["card"], foreground=self.colors["text"])
        self.style.configure(
            "TNotebook",
            background=self.colors["bg"],
            bordercolor=self.colors["border"],
        )
        self.style.configure(
            "TNotebook.Tab",
            background=self.colors["card"],
            foreground=self.colors["muted"],
            padding=(12, 6),
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.colors["accent_light"])],
            foreground=[("selected", self.colors["accent_dark"])],
        )

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root)
        outer.grid(row=0, column=0, sticky=tk.NSEW)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(outer, highlightthickness=0, bg=self.colors["bg"])
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)

        main = ttk.Frame(self.canvas, padding=16, style="Card.TFrame")
        self._canvas_window = self.canvas.create_window((0, 0), window=main, anchor=tk.NW)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)
        main.bind("<Configure>", self._update_scrollregion)
        self.canvas.bind("<Configure>", self._update_canvas_width)
        self._bind_mousewheel(self.canvas)

        form = ttk.LabelFrame(main, text="Configurações", padding=14)
        form.grid(row=0, column=0, sticky=tk.EW)

        self.city_var = tk.StringVar()
        self.country_var = tk.StringVar()
        self.coords_var = tk.StringVar()
        self.name_label_var = tk.StringVar()
        self.country_label_var = tk.StringVar()
        self.distance_var = tk.StringVar(value="29000")
        self.width_var = tk.StringVar(value="305")
        self.height_var = tk.StringVar(value="406")
        self.dpi_var = tk.StringVar(value="300")
        self.theme_var = tk.StringVar(value=self.theme_names[0])
        self.format_var = tk.StringVar(value="png")
        self.all_themes_var = tk.BooleanVar(value=False)
        self.refresh_cache_var = tk.BooleanVar(value=False)
        self.show_city_var = tk.BooleanVar(value=True)
        self.show_country_var = tk.BooleanVar(value=True)
        self.show_coords_var = tk.BooleanVar(value=True)
        self.show_attribution_var = tk.BooleanVar(value=True)
        self.show_line_var = tk.BooleanVar(value=True)
        self.gradient_enabled_var = tk.BooleanVar(value=True)
        self.gradient_percent_var = tk.StringVar(value="25")
        self.gradient_orientation_var = tk.StringVar(value="Vertical (topo/base)")
        self.poi_enabled_var = tk.BooleanVar(value=False)
        self.poi_location_var = tk.StringVar()
        self.poi_size_var = tk.StringVar(value="12")
        self.poi_color_var = tk.StringVar(value="#e53935")
        self.poi_svg_path_var = tk.StringVar()
        self.font_family_var = tk.StringVar()
        self.font_main_size_var = tk.StringVar(value="60")
        self.font_sub_size_var = tk.StringVar(value="22")
        self.font_coords_size_var = tk.StringVar(value="14")
        self.font_attr_size_var = tk.StringVar(value="8")
        self.city_x_var = tk.StringVar(value="0.5")
        self.city_y_var = tk.StringVar(value="0.14")
        self.country_x_var = tk.StringVar(value="0.5")
        self.country_y_var = tk.StringVar(value="0.10")
        self.coords_x_var = tk.StringVar(value="0.5")
        self.coords_y_var = tk.StringVar(value="0.07")
        self.line_x_start_var = tk.StringVar(value="0.4")
        self.line_x_end_var = tk.StringVar(value="0.6")
        self.line_y_var = tk.StringVar(value="0.125")
        self.attr_x_var = tk.StringVar(value="0.98")
        self.attr_y_var = tk.StringVar(value="0.02")
        self.layer_vars: dict[str, tk.BooleanVar] = {}
        self.layer_options = [
            ("roads", "Ruas (hierarquia)", True),
            ("water", "Água (lagos/mar)", True),
            ("rivers", "Rios", True),
            ("oceans", "Oceanos", True),
            ("forests", "Florestas", True),
            ("green_spaces", "Áreas verdes", True),
            ("farmland", "Áreas agrícolas", True),
            ("wetlands", "Zonas úmidas", True),
            ("beaches", "Praias", True),
            ("industrial", "Industrial", True),
            ("residential", "Residencial", True),
            ("buildings", "Edificações", True),
            ("parking", "Estacionamentos", True),
            ("sports", "Esportes", True),
            ("aerodrome", "Aeródromos", True),
            ("runways", "Pistas", True),
            ("railways", "Ferrovias", True),
            ("subtram", "Metrô/Tram", True),
        ]
        self.road_type_vars: dict[str, tk.BooleanVar] = {}
        self.road_type_options = [
            ("path", "Trilhas/Ciclovias", False, False),
            ("service", "Serviço", False, False),
            ("residential", "Residencial", True, False),
            ("tertiary", "Tertiary (+link)", True, True),
            ("secondary", "Secondary (+link)", True, True),
            ("primary", "Primary (+link)", True, True),
            ("trunk", "Trunk (+link)", True, True),
            ("motorway", "Motorway (+link)", True, True),
        ]

        self._add_row(form, 0, "Cidade", self.city_var)
        self._add_row(form, 1, "País", self.country_var)
        self._add_row(form, 2, "Coordenadas (lat, lon)", self.coords_var)
        self._add_row(form, 3, "Nome exibido", self.name_label_var)
        self._add_row(form, 4, "País exibido", self.country_label_var)

        ttk.Label(form, text="Tema").grid(row=5, column=0, sticky=tk.W, pady=6)
        theme_combo = ttk.Combobox(form, textvariable=self.theme_var, values=self.theme_names, state="readonly")
        theme_combo.grid(row=5, column=1, sticky=tk.EW, pady=6)

        ttk.Label(form, text="Formato").grid(row=6, column=0, sticky=tk.W, pady=6)
        format_combo = ttk.Combobox(form, textvariable=self.format_var, values=["png", "svg", "pdf"], state="readonly")
        format_combo.grid(row=6, column=1, sticky=tk.EW, pady=6)

        self._add_row(form, 7, "Distância (m)", self.distance_var)
        self._add_row(form, 8, "Largura (mm)", self.width_var)
        self._add_row(form, 9, "Altura (mm)", self.height_var)
        self._add_row(form, 10, "DPI (png)", self.dpi_var)

        gradient_frame = ttk.LabelFrame(form, text="Gradiente", padding=10)
        gradient_frame.grid(row=11, column=0, columnspan=2, sticky=tk.EW, pady=8)
        gradient_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            gradient_frame,
            text="Aplicar gradiente",
            variable=self.gradient_enabled_var,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))
        ttk.Label(gradient_frame, text="Percentual (%)").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(gradient_frame, textvariable=self.gradient_percent_var, width=8).grid(
            row=1,
            column=1,
            sticky=tk.W,
            pady=4,
        )
        ttk.Label(gradient_frame, text="Orientação").grid(row=2, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(
            gradient_frame,
            textvariable=self.gradient_orientation_var,
            values=["Vertical (topo/base)", "Horizontal (esq/dir)", "Ambos"],
            state="readonly",
            width=24,
        ).grid(row=2, column=1, sticky=tk.W, pady=4)

        options = ttk.Frame(form, style="Card.TFrame")
        options.grid(row=12, column=0, columnspan=2, sticky=tk.W, pady=8)
        ttk.Checkbutton(options, text="Gerar todos os temas", variable=self.all_themes_var).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(options, text="Atualizar cache", variable=self.refresh_cache_var).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Button(options, text="Listar temas", command=self.show_themes, style="Secondary.TButton").pack(
            side=tk.LEFT, padx=(0, 16)
        )
        ttk.Button(options, text="Salvar configuração", command=self.save_config, style="Secondary.TButton").pack(
            side=tk.LEFT, padx=(0, 16)
        )
        ttk.Button(options, text="Carregar configuração", command=self.load_config, style="Secondary.TButton").pack(
            side=tk.LEFT
        )

        form.columnconfigure(1, weight=1)

        text_frame = ttk.LabelFrame(main, text="Texto no mapa", padding=12)
        text_frame.grid(row=1, column=0, sticky=tk.EW)
        text_frame.columnconfigure(1, weight=1)

        show_row = ttk.Frame(text_frame, style="Card.TFrame")
        show_row.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=4)
        ttk.Checkbutton(show_row, text="Cidade", variable=self.show_city_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(show_row, text="País", variable=self.show_country_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(show_row, text="Coordenadas", variable=self.show_coords_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(show_row, text="Crédito OSM", variable=self.show_attribution_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(show_row, text="Linha separadora", variable=self.show_line_var).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(text_frame, text="Fonte (Google Fonts ou vazio p/ padrão)").grid(row=1, column=0, sticky=tk.W, pady=6)
        font_options = [""] + self.local_font_families
        ttk.Combobox(
            text_frame,
            textvariable=self.font_family_var,
            values=font_options,
            state="readonly",
            style="TCombobox",
        ).grid(row=1, column=1, sticky=tk.EW, pady=6)

        text_grid = ttk.Frame(text_frame, style="Card.TFrame", padding=6)
        text_grid.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=4)
        for column in range(1, 6):
            text_grid.columnconfigure(column, weight=1)
        ttk.Label(text_grid, text="").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(text_grid, text="Cidade").grid(row=0, column=1, sticky=tk.W, padx=(4, 4))
        ttk.Label(text_grid, text="País").grid(row=0, column=2, sticky=tk.W, padx=(4, 4))
        ttk.Label(text_grid, text="Coords").grid(row=0, column=3, sticky=tk.W, padx=(4, 4))
        ttk.Label(text_grid, text="Linha").grid(row=0, column=4, sticky=tk.W, padx=(4, 4))
        ttk.Label(text_grid, text="Crédito").grid(row=0, column=5, sticky=tk.W, padx=(4, 4))

        ttk.Label(text_grid, text="Tamanho (pt)").grid(row=1, column=0, sticky=tk.W, pady=(4, 2))
        ttk.Entry(text_grid, textvariable=self.font_main_size_var, width=6).grid(row=1, column=1, sticky=tk.W, padx=4)
        ttk.Entry(text_grid, textvariable=self.font_sub_size_var, width=6).grid(row=1, column=2, sticky=tk.W, padx=4)
        ttk.Entry(text_grid, textvariable=self.font_coords_size_var, width=6).grid(row=1, column=3, sticky=tk.W, padx=4)
        ttk.Label(text_grid, text="—").grid(row=1, column=4, sticky=tk.W, padx=4)
        ttk.Entry(text_grid, textvariable=self.font_attr_size_var, width=6).grid(row=1, column=5, sticky=tk.W, padx=4)

        ttk.Label(text_grid, text="Posição X").grid(row=2, column=0, sticky=tk.W, pady=(4, 2))
        ttk.Entry(text_grid, textvariable=self.city_x_var, width=6).grid(row=2, column=1, sticky=tk.W, padx=4)
        ttk.Entry(text_grid, textvariable=self.country_x_var, width=6).grid(row=2, column=2, sticky=tk.W, padx=4)
        ttk.Entry(text_grid, textvariable=self.coords_x_var, width=6).grid(row=2, column=3, sticky=tk.W, padx=4)
        line_x_frame = ttk.Frame(text_grid, style="Card.TFrame")
        line_x_frame.grid(row=2, column=4, sticky=tk.W, padx=4)
        ttk.Entry(line_x_frame, textvariable=self.line_x_start_var, width=6).pack(side=tk.LEFT)
        ttk.Label(line_x_frame, text="→").pack(side=tk.LEFT, padx=2)
        ttk.Entry(line_x_frame, textvariable=self.line_x_end_var, width=6).pack(side=tk.LEFT)
        ttk.Entry(text_grid, textvariable=self.attr_x_var, width=6).grid(row=2, column=5, sticky=tk.W, padx=4)

        ttk.Label(text_grid, text="Posição Y").grid(row=3, column=0, sticky=tk.W, pady=(4, 2))
        ttk.Entry(text_grid, textvariable=self.city_y_var, width=6).grid(row=3, column=1, sticky=tk.W, padx=4)
        ttk.Entry(text_grid, textvariable=self.country_y_var, width=6).grid(row=3, column=2, sticky=tk.W, padx=4)
        ttk.Entry(text_grid, textvariable=self.coords_y_var, width=6).grid(row=3, column=3, sticky=tk.W, padx=4)
        ttk.Entry(text_grid, textvariable=self.line_y_var, width=6).grid(row=3, column=4, sticky=tk.W, padx=4)
        ttk.Entry(text_grid, textvariable=self.attr_y_var, width=6).grid(row=3, column=5, sticky=tk.W, padx=4)

        actions = ttk.Frame(main, padding=(0, 16, 0, 16), style="Card.TFrame")
        actions.grid(row=2, column=0, sticky=tk.EW)
        self.generate_button = ttk.Button(actions, text="Gerar pôster", command=self.start_generation)
        self.generate_button.pack(side=tk.RIGHT)

        options_tabs = ttk.Notebook(main)
        options_tabs.grid(row=3, column=0, sticky=tk.EW)

        layers_frame = ttk.Frame(options_tabs, padding=10, style="Card.TFrame")
        options_tabs.add(layers_frame, text="Camadas OSMnx")
        layers_frame.columnconfigure(0, weight=1)
        layers_frame.columnconfigure(1, weight=1)
        for index, (key, label, default) in enumerate(self.layer_options):
            var = tk.BooleanVar(value=default)
            self.layer_vars[key] = var
            column = index % 2
            row = index // 2
            ttk.Checkbutton(layers_frame, text=label, variable=var).grid(row=row, column=column, sticky=tk.W)

        roads_frame = ttk.Frame(options_tabs, padding=10, style="Card.TFrame")
        options_tabs.add(roads_frame, text="Ruas")
        roads_frame.columnconfigure(0, weight=1)
        roads_frame.columnconfigure(1, weight=1)
        for index, (key, label, default, _) in enumerate(self.road_type_options):
            var = tk.BooleanVar(value=default)
            self.road_type_vars[key] = var
            column = index % 2
            row = index // 2
            ttk.Checkbutton(roads_frame, text=label, variable=var).grid(row=row, column=column, sticky=tk.W)

        poi_frame = ttk.Frame(options_tabs, padding=10, style="Card.TFrame")
        options_tabs.add(poi_frame, text="Ponto de interesse")
        poi_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(
            poi_frame,
            text="Adicionar ponto de interesse",
            variable=self.poi_enabled_var,
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))
        ttk.Button(
            poi_frame,
            text="Adicionar ao mapa",
            command=self._enable_poi,
            style="Secondary.TButton",
        ).grid(row=0, column=1, sticky=tk.E, pady=(0, 8))
        ttk.Label(poi_frame, text="Link Google Maps ou lat, lon").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(poi_frame, textvariable=self.poi_location_var, style="Text.TEntry").grid(
            row=1, column=1, sticky=tk.EW, pady=4
        )
        ttk.Label(poi_frame, text="SVG do marcador").grid(row=2, column=0, sticky=tk.W, pady=4)
        svg_row = ttk.Frame(poi_frame, style="Card.TFrame")
        svg_row.grid(row=2, column=1, sticky=tk.EW, pady=4)
        svg_row.columnconfigure(0, weight=1)
        ttk.Entry(svg_row, textvariable=self.poi_svg_path_var, style="Text.TEntry").grid(
            row=0, column=0, sticky=tk.EW
        )
        ttk.Button(svg_row, text="Selecionar", command=self._select_poi_svg, style="Secondary.TButton").grid(
            row=0, column=1, padx=(6, 0)
        )
        ttk.Label(poi_frame, text="Tamanho (pt)").grid(row=3, column=0, sticky=tk.W, pady=4)
        ttk.Entry(poi_frame, textvariable=self.poi_size_var, width=8).grid(row=3, column=1, sticky=tk.W, pady=4)
        ttk.Label(poi_frame, text="Cor (hex)").grid(row=4, column=0, sticky=tk.W, pady=4)
        color_row = ttk.Frame(poi_frame, style="Card.TFrame")
        color_row.grid(row=4, column=1, sticky=tk.W, pady=4)
        ttk.Entry(color_row, textvariable=self.poi_color_var, width=12).pack(side=tk.LEFT)
        self.poi_color_preview = tk.Canvas(color_row, width=22, height=22, highlightthickness=1)
        self.poi_color_preview.pack(side=tk.LEFT, padx=(8, 0))
        self._update_poi_color_preview()
        self.poi_color_var.trace_add("write", self._update_poi_color_preview)

        log_frame = ttk.LabelFrame(main, text="Logs", padding=12)
        log_frame.grid(row=4, column=0, sticky=tk.NSEW)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(
            log_frame,
            height=12,
            state=tk.DISABLED,
            background="white",
            foreground=self.colors["text"],
            borderwidth=1,
            relief="solid",
        )
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)

    def _bind_mousewheel(self, widget: tk.Widget) -> None:
        def on_enter(_: tk.Event) -> None:
            widget.bind_all("<MouseWheel>", self._on_mousewheel)
            widget.bind_all("<Button-4>", self._on_mousewheel)
            widget.bind_all("<Button-5>", self._on_mousewheel)

        def on_leave(_: tk.Event) -> None:
            widget.unbind_all("<MouseWheel>")
            widget.unbind_all("<Button-4>")
            widget.unbind_all("<Button-5>")

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")

    def _update_scrollregion(self, _: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _update_canvas_width(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._canvas_window, width=event.width)

    def _add_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=6)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=6)

    def _enable_poi(self) -> None:
        self.poi_enabled_var.set(True)
        self.log("Ponto de interesse ativado.")

    def _select_poi_svg(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Selecionar SVG do marcador",
            filetypes=[("SVG", "*.svg"), ("Todos os arquivos", "*.*")],
        )
        if file_path:
            self.poi_svg_path_var.set(file_path)

    def _update_poi_color_preview(self, *_: object) -> None:
        color = self.poi_color_var.get().strip() or "#ffffff"
        try:
            self.poi_color_preview.configure(background=color)
        except tk.TclError:
            self.poi_color_preview.configure(background="#ffffff")

    def _parse_coordinates(self, value: str) -> tuple[float, float]:
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 2:
            raise ValueError("Informe coordenadas no formato: lat, lon.")
        try:
            lat = parse(parts[0])
            lon = parse(parts[1])
        except ValueError as exc:
            raise ValueError(
                "Coordenadas inválidas. Use números decimais ou DMS com direção (ex: 23°30'0\"S)."
            ) from exc
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Coordenadas fora do intervalo permitido.")
        return (lat, lon)

    def _extract_google_maps_coordinates(self, url: str) -> tuple[float, float] | None:
        patterns = [
            r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
            r"[?&]q=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
            r"[?&]query=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
            r"[?&]ll=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return (float(match.group(1)), float(match.group(2)))
        return None

    def _parse_poi_location(self, value: str) -> tuple[float, float]:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Informe o link ou coordenadas do ponto de interesse.")
        if cleaned.startswith("http"):
            coords = self._extract_google_maps_coordinates(cleaned)
            if coords is None:
                raise ValueError("Não foi possível extrair coordenadas do link do Google Maps.")
            return coords
        return self._parse_coordinates(cleaned)

    def _get_gradient_orientation(self) -> str:
        mapping = {
            "Vertical (topo/base)": "vertical",
            "Horizontal (esq/dir)": "horizontal",
            "Ambos": "both",
        }
        selection = self.gradient_orientation_var.get()
        return mapping.get(selection, "vertical")

    def log(self, message: str) -> None:
        def append() -> None:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.root.after(0, append)

    def show_themes(self) -> None:
        themes = ", ".join(self.theme_names)
        self.log(f"Temas disponíveis: {themes}")
        messagebox.showinfo("Temas disponíveis", themes)

    def _build_config(self) -> dict:
        enabled_layers = [key for key, _, _ in self.layer_options if self.layer_vars[key].get()]
        selected_road_types = [key for key, _, _, _ in self.road_type_options if self.road_type_vars[key].get()]
        return {
            "city": self.city_var.get().strip(),
            "country": self.country_var.get().strip(),
            "coords": self.coords_var.get().strip(),
            "name_label": self.name_label_var.get().strip(),
            "country_label": self.country_label_var.get().strip(),
            "distance": self.distance_var.get().strip(),
            "width_mm": self.width_var.get().strip(),
            "height_mm": self.height_var.get().strip(),
            "dpi": self.dpi_var.get().strip(),
            "theme": self.theme_var.get().strip(),
            "format": self.format_var.get().strip(),
            "all_themes": self.all_themes_var.get(),
            "refresh_cache": self.refresh_cache_var.get(),
            "gradient": {
                "enabled": self.gradient_enabled_var.get(),
                "percent": self.gradient_percent_var.get().strip(),
                "orientation": self._get_gradient_orientation(),
            },
            "poi": {
                "enabled": self.poi_enabled_var.get(),
                "location": self.poi_location_var.get().strip(),
                "svg_path": self.poi_svg_path_var.get().strip(),
                "size": self.poi_size_var.get().strip(),
                "color": self.poi_color_var.get().strip(),
            },
            "text_options": {
                "show_city": self.show_city_var.get(),
                "show_country": self.show_country_var.get(),
                "show_coords": self.show_coords_var.get(),
                "show_attribution": self.show_attribution_var.get(),
                "show_line": self.show_line_var.get(),
                "font_family": self.font_family_var.get().strip(),
                "main_size": self.font_main_size_var.get().strip(),
                "sub_size": self.font_sub_size_var.get().strip(),
                "coords_size": self.font_coords_size_var.get().strip(),
                "attr_size": self.font_attr_size_var.get().strip(),
                "city_pos": {"x": self.city_x_var.get().strip(), "y": self.city_y_var.get().strip()},
                "country_pos": {"x": self.country_x_var.get().strip(), "y": self.country_y_var.get().strip()},
                "coords_pos": {"x": self.coords_x_var.get().strip(), "y": self.coords_y_var.get().strip()},
                "line_x": {"start": self.line_x_start_var.get().strip(), "end": self.line_x_end_var.get().strip()},
                "line_y": self.line_y_var.get().strip(),
                "attr_pos": {"x": self.attr_x_var.get().strip(), "y": self.attr_y_var.get().strip()},
            },
            "enabled_layers": enabled_layers,
            "road_types": selected_road_types,
            "version": 1,
        }

    def save_config(self) -> None:
        file_path = filedialog.asksaveasfilename(
            title="Salvar configuração",
            defaultextension=".json",
            filetypes=[("Configuração do pôster", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return
        config = self._build_config()
        try:
            with open(file_path, "w", encoding="utf-8") as handle:
                json.dump(config, handle, ensure_ascii=False, indent=2)
            self.log(f"Configuração salva em: {file_path}")
            messagebox.showinfo("Configuração salva", "Configuração salva com sucesso.")
        except OSError as exc:
            self.log(f"Erro ao salvar configuração: {exc}")
            messagebox.showerror("Erro ao salvar", str(exc))

    def load_config(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Carregar configuração",
            filetypes=[("Configuração do pôster", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                config = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self.log(f"Erro ao carregar configuração: {exc}")
            messagebox.showerror("Erro ao carregar", str(exc))
            return

        self.city_var.set(str(config.get("city", "")))
        self.country_var.set(str(config.get("country", "")))
        self.coords_var.set(str(config.get("coords", "")))
        self.name_label_var.set(str(config.get("name_label", "")))
        self.country_label_var.set(str(config.get("country_label", "")))
        self.distance_var.set(str(config.get("distance", self.distance_var.get())))
        self.width_var.set(str(config.get("width_mm", self.width_var.get())))
        self.height_var.set(str(config.get("height_mm", self.height_var.get())))
        self.dpi_var.set(str(config.get("dpi", self.dpi_var.get())))

        theme = config.get("theme")
        if isinstance(theme, str) and theme in self.theme_names:
            self.theme_var.set(theme)
        elif theme:
            self.log(f"Tema '{theme}' não encontrado. Mantendo tema atual.")

        output_format = config.get("format")
        if output_format in {"png", "svg", "pdf"}:
            self.format_var.set(output_format)
        elif output_format:
            self.log(f"Formato '{output_format}' inválido. Mantendo formato atual.")

        self.all_themes_var.set(bool(config.get("all_themes", False)))
        self.refresh_cache_var.set(bool(config.get("refresh_cache", False)))
        gradient = config.get("gradient", {})
        if isinstance(gradient, dict):
            self.gradient_enabled_var.set(bool(gradient.get("enabled", True)))
            if "percent" in gradient:
                self.gradient_percent_var.set(str(gradient.get("percent", "25")))
            orientation = gradient.get("orientation")
            orientation_map = {
                "vertical": "Vertical (topo/base)",
                "horizontal": "Horizontal (esq/dir)",
                "both": "Ambos",
            }
            if isinstance(orientation, str):
                self.gradient_orientation_var.set(orientation_map.get(orientation.lower(), "Vertical (topo/base)"))

        poi = config.get("poi", {})
        if isinstance(poi, dict):
            self.poi_enabled_var.set(bool(poi.get("enabled", False)))
            self.poi_location_var.set(str(poi.get("location", "")))
            self.poi_svg_path_var.set(str(poi.get("svg_path", "")))
            self.poi_size_var.set(str(poi.get("size", self.poi_size_var.get())))
            self.poi_color_var.set(str(poi.get("color", self.poi_color_var.get())))

        text_options = config.get("text_options", {})
        if isinstance(text_options, dict):
            self.show_city_var.set(bool(text_options.get("show_city", True)))
            self.show_country_var.set(bool(text_options.get("show_country", True)))
            self.show_coords_var.set(bool(text_options.get("show_coords", True)))
            self.show_attribution_var.set(bool(text_options.get("show_attribution", True)))
            self.show_line_var.set(bool(text_options.get("show_line", True)))
            self.font_family_var.set(str(text_options.get("font_family", "")))
            self.font_main_size_var.set(str(text_options.get("main_size", self.font_main_size_var.get())))
            self.font_sub_size_var.set(str(text_options.get("sub_size", self.font_sub_size_var.get())))
            self.font_coords_size_var.set(str(text_options.get("coords_size", self.font_coords_size_var.get())))
            self.font_attr_size_var.set(str(text_options.get("attr_size", self.font_attr_size_var.get())))

            city_pos = text_options.get("city_pos", {})
            if isinstance(city_pos, dict):
                self.city_x_var.set(str(city_pos.get("x", self.city_x_var.get())))
                self.city_y_var.set(str(city_pos.get("y", self.city_y_var.get())))
            country_pos = text_options.get("country_pos", {})
            if isinstance(country_pos, dict):
                self.country_x_var.set(str(country_pos.get("x", self.country_x_var.get())))
                self.country_y_var.set(str(country_pos.get("y", self.country_y_var.get())))
            coords_pos = text_options.get("coords_pos", {})
            if isinstance(coords_pos, dict):
                self.coords_x_var.set(str(coords_pos.get("x", self.coords_x_var.get())))
                self.coords_y_var.set(str(coords_pos.get("y", self.coords_y_var.get())))
            line_x = text_options.get("line_x", {})
            if isinstance(line_x, dict):
                self.line_x_start_var.set(str(line_x.get("start", self.line_x_start_var.get())))
                self.line_x_end_var.set(str(line_x.get("end", self.line_x_end_var.get())))
            self.line_y_var.set(str(text_options.get("line_y", self.line_y_var.get())))
            attr_pos = text_options.get("attr_pos", {})
            if isinstance(attr_pos, dict):
                self.attr_x_var.set(str(attr_pos.get("x", self.attr_x_var.get())))
                self.attr_y_var.set(str(attr_pos.get("y", self.attr_y_var.get())))

        enabled_layers = config.get("enabled_layers")
        if isinstance(enabled_layers, list):
            enabled_set = {layer for layer in enabled_layers if isinstance(layer, str)}
            for key, _, _ in self.layer_options:
                self.layer_vars[key].set(key in enabled_set)

        road_types = config.get("road_types")
        if isinstance(road_types, list):
            road_set = {road for road in road_types if isinstance(road, str)}
            option_map = {key: include_link for key, _, _, include_link in self.road_type_options}
            for key in option_map:
                include_link = option_map[key]
                self.road_type_vars[key].set(
                    key in road_set or (include_link and f"{key}_link" in road_set)
                )
        self.log(f"Configuração carregada de: {file_path}")
        messagebox.showinfo("Configuração carregada", "Configuração carregada com sucesso.")


    def _ensure_poster_module(self) -> bool:
        if poster is not None:
            return True

        missing = POSTER_IMPORT_ERROR.name if POSTER_IMPORT_ERROR else "dependência desconhecida"
        message = (
            f"Não foi possível carregar o gerador de pôsteres porque a dependência '{missing}' "
            "não está instalada. Execute: pip install -r requirements.txt"
        )
        self.log(message)
        messagebox.showerror("Dependência em falta", message)
        return False

    def start_generation(self) -> None:
        if self.generate_button["state"] == tk.DISABLED:
            return
        if not self._ensure_poster_module():
            return

        self.generate_button.config(state=tk.DISABLED)
        self.log("Iniciando geração...")
        thread = threading.Thread(target=self._run_generation, daemon=True)
        thread.start()

    def _run_generation(self) -> None:
        try:
            city = self.city_var.get().strip()
            country = self.country_var.get().strip()
            coords_input = self.coords_var.get().strip()
            if coords_input:
                coords = self._parse_coordinates(coords_input)
                if not city:
                    city = self.name_label_var.get().strip() or "Coordenadas"
                if not country:
                    country = self.country_label_var.get().strip()
                self.log(f"Usando coordenadas: {coords[0]}, {coords[1]}")
            else:
                if not city or not country:
                    raise ValueError("Cidade e país são obrigatórios quando as coordenadas não são informadas.")
                coords = poster.get_coordinates(city, country, self.refresh_cache_var.get())

            distance = int(self.distance_var.get())
            width_mm = float(self.width_var.get())
            height_mm = float(self.height_var.get())
            width = width_mm / 25.4
            height = height_mm / 25.4
            dpi = int(self.dpi_var.get())
            output_format = self.format_var.get()
            gradient_percent = float(self.gradient_percent_var.get())

            themes_to_generate = self.theme_names if self.all_themes_var.get() else [self.theme_var.get()]
            self.log(f"Temas selecionados: {', '.join(themes_to_generate)}")
            selected_layers = [key for key, _, _ in self.layer_options if self.layer_vars[key].get()]
            selected_labels = [label for key, label, _ in self.layer_options if self.layer_vars[key].get()]
            selected_road_bases = [key for key, _, _, _ in self.road_type_options if self.road_type_vars[key].get()]
            selected_road_types = []
            option_map = {key: include_link for key, _, _, include_link in self.road_type_options}
            for base in selected_road_bases:
                selected_road_types.append(base)
                if option_map.get(base):
                    selected_road_types.append(f"{base}_link")
            if selected_road_bases:
                self.log(f"Tipos de rua: {', '.join(selected_road_bases)} (+ links)")
            else:
                self.log("Tipos de rua: nenhum")
            if selected_labels:
                self.log(f"Camadas OSMnx: {', '.join(selected_labels)}")
            else:
                self.log("Camadas OSMnx: nenhuma")
            for theme_name in themes_to_generate:
                self.log(f"Gerando tema: {theme_name}")
                poster.THEME = load_theme(theme_name)
                output_file = poster.generate_output_filename(city, country, theme_name, output_format)
                text_options = {
                    "show_city": self.show_city_var.get(),
                    "show_country": self.show_country_var.get(),
                    "show_coords": self.show_coords_var.get(),
                    "show_attribution": self.show_attribution_var.get(),
                    "show_line": self.show_line_var.get(),
                    "font_family": self.font_family_var.get().strip() or None,
                    "main_size": float(self.font_main_size_var.get()),
                    "sub_size": float(self.font_sub_size_var.get()),
                    "coords_size": float(self.font_coords_size_var.get()),
                    "attr_size": float(self.font_attr_size_var.get()),
                    "city_pos": (float(self.city_x_var.get()), float(self.city_y_var.get())),
                    "country_pos": (float(self.country_x_var.get()), float(self.country_y_var.get())),
                    "coords_pos": (float(self.coords_x_var.get()), float(self.coords_y_var.get())),
                    "line_x": (float(self.line_x_start_var.get()), float(self.line_x_end_var.get())),
                    "line_y": float(self.line_y_var.get()),
                    "attr_pos": (float(self.attr_x_var.get()), float(self.attr_y_var.get())),
                }
                gradient_orientation = self._get_gradient_orientation()
                gradient_sides_map = {
                    "vertical": ["bottom", "top"],
                    "horizontal": ["left", "right"],
                    "both": ["bottom", "top", "left", "right"],
                }
                poster_kwargs = {
                    "width": width,
                    "height": height,
                    "dpi": dpi,
                    "country_label": self.country_label_var.get().strip() or None,
                    "name_label": self.name_label_var.get().strip() or None,
                    "refresh_cache": self.refresh_cache_var.get(),
                }
                if self.gradient_enabled_var.get():
                    poster_kwargs["gradient_sides"] = gradient_sides_map.get(gradient_orientation, ["bottom", "top"])
                else:
                    poster_kwargs["gradient_sides"] = None
                poster_kwargs["fade_fraction"] = gradient_percent / 100
                if self.poi_enabled_var.get():
                    poi_coords = self._parse_poi_location(self.poi_location_var.get())
                    poi_size = float(self.poi_size_var.get())
                    if poi_size <= 0:
                        raise ValueError("O tamanho do ponto de interesse deve ser maior que zero.")
                    poster_kwargs["poi_options"] = {
                        "coords": poi_coords,
                        "svg_path": self.poi_svg_path_var.get().strip(),
                        "size": poi_size,
                        "color": self.poi_color_var.get().strip(),
                    }
                create_sig = inspect.signature(poster.create_poster)
                has_kwargs = any(
                    param.kind == inspect.Parameter.VAR_KEYWORD for param in create_sig.parameters.values()
                )
                if "road_types" in create_sig.parameters or has_kwargs:
                    poster_kwargs["road_types"] = selected_road_types
                elif selected_road_types:
                    self.log("Aviso: esta versão do gerador não suporta filtro de tipos de rua na GUI.")
                if "enabled_layers" in create_sig.parameters or has_kwargs:
                    poster_kwargs["enabled_layers"] = selected_layers
                elif selected_layers:
                    self.log("Aviso: esta versão do gerador não suporta filtro de camadas OSM na GUI.")
                if "text_options" in create_sig.parameters or has_kwargs:
                    poster_kwargs["text_options"] = text_options
                poster.create_poster(
                    city,
                    country,
                    coords,
                    distance,
                    output_file,
                    output_format,
                    **poster_kwargs,
                )

            self.log("Geração concluída com sucesso!")
            self.root.after(0, lambda: messagebox.showinfo("Sucesso", "Pôster(s) gerado(s) com sucesso."))
        except Exception as exc:
            self.log(f"Erro: {exc}")
            self.root.after(0, lambda err=exc: messagebox.showerror("Erro", str(err)))
        finally:
            self.root.after(0, lambda: self.generate_button.config(state=tk.NORMAL))


def main() -> None:
    root = tk.Tk()
    app = PosterApp(root)
    if app.theme_names:
        root.mainloop()


if __name__ == "__main__":
    main()
