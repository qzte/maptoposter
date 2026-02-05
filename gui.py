import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import create_map_poster as poster
from map_poster.theme_management import get_available_themes, load_theme


class PosterApp:
    OSMNX_LAYERS = [
        "water (natural=water/bay/strait, waterway=riverbank/dock/canal)",
        "rivers (waterway=river/stream)",
        "coastline (natural=coastline)",
        "forests (natural=wood, landuse=forest/logging)",
        "green spaces (natural=grassland, landuse=grass/recreation_ground/greenfield/meadow/vineyard, leisure=park/garden)",
        "farmland (landuse=farmland, natural=heath/scrub)",
        "wetlands (natural=wetland, landuse=salt_pond)",
        "beaches (natural=beach/sand)",
        "industrial (landuse=industrial/commercial/construction)",
        "residential (landuse=residential)",
        "buildings (building=*)",
        "parking (amenity=parking, parking=surface/multi-storey/underground)",
        "sports (leisure=stadium/sports_centre/pitch)",
        "aerodrome (aeroway=aerodrome)",
        "runways (aeroway=runway/taxiway)",
        "railways (rail/narrow_gauge/monorail/light_rail)",
        "subtram (subway/funicular/tram)",
    ]

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("City Map Poster Generator")
        self.root.geometry("900x700")
        self.root.minsize(760, 600)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.theme_names = get_available_themes()
        if not self.theme_names:
            messagebox.showerror("Erro", "Nenhum tema encontrado em themes/.")
            self.root.destroy()
            return

        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.grid(row=0, column=0, sticky=tk.NSEW)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(5, weight=1)

        form = ttk.LabelFrame(main, text="Configurações", padding=12)
        form.grid(row=0, column=0, sticky=tk.EW)

        self.city_var = tk.StringVar()
        self.country_var = tk.StringVar()
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
        self.osm_hierarchy_var = tk.BooleanVar(value=False)
        self.typography_position_var = tk.BooleanVar(value=False)
        self.osmnx_patterns_var = tk.BooleanVar(value=False)

        self._add_row(form, 0, "Cidade", self.city_var)
        self._add_row(form, 1, "País", self.country_var)
        self._add_row(form, 2, "Nome exibido", self.name_label_var)
        self._add_row(form, 3, "País exibido", self.country_label_var)

        ttk.Label(form, text="Tema").grid(row=4, column=0, sticky=tk.W, pady=6)
        theme_combo = ttk.Combobox(form, textvariable=self.theme_var, values=self.theme_names, state="readonly")
        theme_combo.grid(row=4, column=1, sticky=tk.EW, pady=6)

        ttk.Label(form, text="Formato").grid(row=5, column=0, sticky=tk.W, pady=6)
        format_combo = ttk.Combobox(form, textvariable=self.format_var, values=["png", "svg", "pdf"], state="readonly")
        format_combo.grid(row=5, column=1, sticky=tk.EW, pady=6)

        self._add_row(form, 6, "Distância (m)", self.distance_var)
        self._add_row(form, 7, "Largura (mm)", self.width_var)
        self._add_row(form, 8, "Altura (mm)", self.height_var)
        self._add_row(form, 9, "DPI (png)", self.dpi_var)

        options = ttk.Frame(form)
        options.grid(row=10, column=0, columnspan=2, sticky=tk.EW, pady=8)
        options.columnconfigure(2, weight=1)
        ttk.Checkbutton(options, text="Gerar todos os temas", variable=self.all_themes_var).grid(row=0, column=0, sticky=tk.W, padx=(0, 16))
        ttk.Checkbutton(options, text="Atualizar cache", variable=self.refresh_cache_var).grid(row=0, column=1, sticky=tk.W, padx=(0, 16))
        ttk.Button(options, text="Listar temas", command=self.show_themes).grid(row=0, column=2, sticky=tk.W)
        ttk.Button(options, text="Listar camadas OSMnx", command=self.show_osmnx_layers).grid(row=0, column=3, sticky=tk.W, padx=(12, 0))

        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(main, padding=(0, 12, 0, 12))
        actions.grid(row=1, column=0, sticky=tk.EW)
        self.generate_button = ttk.Button(actions, text="Gerar pôster", command=self.start_generation)
        self.generate_button.pack(side=tk.RIGHT)

        tips = ttk.LabelFrame(main, text="Dicas rápidas", padding=8)
        tips.grid(row=2, column=0, sticky=tk.EW)
        tips_text = (
            "Distância sugerida: 4000–6000m (pequenas), 8000–12000m (médias), "
            "15000–20000m (grandes).\n"
            "Resolução 300 DPI: Instagram 91x91 mm, A4 210x297 mm, 4K 325x183 mm.\n"
            "Hierarquia de vias: motorway > trunk/primary > secondary > tertiary > residential.\n"
            "Tipografia (y em 0-1): cidade 0.14, linha 0.125, país 0.10, coords 0.07, crédito 0.02.\n"
            "OSMnx: buildings tags={'building': True}, cafés tags={'amenity': 'cafe'}, redes drive/bike/walk."
        )
        self.tips_label = ttk.Label(tips, text=tips_text, justify=tk.LEFT, wraplength=720)
        self.tips_label.pack(anchor=tk.W, fill=tk.X)

        osmnx_frame = ttk.LabelFrame(main, text="Camadas OSMnx disponíveis", padding=8)
        osmnx_frame.grid(row=3, column=0, sticky=tk.EW)
        osmnx_frame.columnconfigure(0, weight=1)
        self.osmnx_list = ScrolledText(osmnx_frame, height=6, state=tk.DISABLED)
        self.osmnx_list.grid(row=0, column=0, sticky=tk.EW)
        self._populate_osmnx_layers()

        reference_frame = ttk.LabelFrame(main, text="Referências opcionais", padding=8)
        reference_frame.grid(row=4, column=0, sticky=tk.EW)
        ttk.Checkbutton(
            reference_frame,
            text="OSM Highway Types → Road Hierarchy",
            variable=self.osm_hierarchy_var,
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            reference_frame,
            text="Typography Positioning (ax.transAxes)",
            variable=self.typography_position_var,
        ).pack(anchor=tk.W)
        ttk.Checkbutton(
            reference_frame,
            text="Useful OSMnx Patterns",
            variable=self.osmnx_patterns_var,
        ).pack(anchor=tk.W)

        log_frame = ttk.LabelFrame(main, text="Logs", padding=8)
        log_frame.grid(row=5, column=0, sticky=tk.NSEW)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(log_frame, height=12, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)

        self.root.bind("<Configure>", self._on_resize)

    def _on_resize(self, event: tk.Event) -> None:
        if event.widget is self.root:
            padding = 96
            wrap = max(240, event.width - padding)
            self.tips_label.configure(wraplength=wrap)
            self.osmnx_list.configure(width=max(40, int(event.width / 12)))

    def _add_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=6)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=6)

    def _log_reference_notes(self) -> None:
        notes: list[str] = []
        if self.osm_hierarchy_var.get():
            notes.append(
                "OSM Highway Types → Road Hierarchy: motorway/motorway_link (1.2), "
                "trunk/primary (1.0), secondary (0.8), tertiary (0.6), "
                "residential/living_street (0.4)."
            )
        if self.typography_position_var.get():
            notes.append(
                "Typography Positioning (ax.transAxes): y=0.14 cidade, y=0.125 linha, "
                "y=0.10 país, y=0.07 coordenadas, y=0.02 crédito."
            )
        if self.osmnx_patterns_var.get():
            notes.append(
                "Useful OSMnx Patterns: features_from_point(building=True, amenity='cafe'); "
                "graph_from_point(network_type='drive'|'bike'|'walk')."
            )

        if notes:
            self.log("Referências selecionadas:")
            for note in notes:
                self.log(f"- {note}")

    def log(self, message: str) -> None:
        def append() -> None:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.root.after(0, append)

    def _populate_osmnx_layers(self) -> None:
        self.osmnx_list.configure(state=tk.NORMAL)
        self.osmnx_list.delete("1.0", tk.END)
        for layer in self.OSMNX_LAYERS:
            self.osmnx_list.insert(tk.END, f"• {layer}\n")
        self.osmnx_list.configure(state=tk.DISABLED)

    def show_themes(self) -> None:
        themes = ", ".join(self.theme_names)
        self.log(f"Temas disponíveis: {themes}")
        messagebox.showinfo("Temas disponíveis", themes)

    def show_osmnx_layers(self) -> None:
        layers = "\n".join(f"- {layer}" for layer in self.OSMNX_LAYERS)
        self.log("Camadas OSMnx disponíveis:")
        for layer in self.OSMNX_LAYERS:
            self.log(f"- {layer}")
        messagebox.showinfo("Camadas OSMnx disponíveis", layers)

    def start_generation(self) -> None:
        if self.generate_button["state"] == tk.DISABLED:
            return

        self.generate_button.config(state=tk.DISABLED)
        self.log("Iniciando geração...")
        thread = threading.Thread(target=self._run_generation, daemon=True)
        thread.start()

    def _run_generation(self) -> None:
        try:
            city = self.city_var.get().strip()
            country = self.country_var.get().strip()
            if not city or not country:
                raise ValueError("Cidade e país são obrigatórios.")

            self._log_reference_notes()
            distance = int(self.distance_var.get())
            width_mm = float(self.width_var.get())
            height_mm = float(self.height_var.get())
            width = width_mm / 25.4
            height = height_mm / 25.4
            dpi = int(self.dpi_var.get())
            output_format = self.format_var.get()

            themes_to_generate = self.theme_names if self.all_themes_var.get() else [self.theme_var.get()]
            self.log(f"Temas selecionados: {', '.join(themes_to_generate)}")
            coords = poster.get_coordinates(city, country, self.refresh_cache_var.get())

            for theme_name in themes_to_generate:
                self.log(f"Gerando tema: {theme_name}")
                poster.THEME = load_theme(theme_name)
                output_file = poster.generate_output_filename(city, theme_name, output_format)
                poster.create_poster(
                    city,
                    country,
                    coords,
                    distance,
                    output_file,
                    output_format,
                    width=width,
                    height=height,
                    dpi=dpi,
                    country_label=self.country_label_var.get().strip() or None,
                    name_label=self.name_label_var.get().strip() or None,
                    refresh_cache=self.refresh_cache_var.get(),
                )

            self.log("Geração concluída com sucesso!")
            self.root.after(0, lambda: messagebox.showinfo("Sucesso", "Pôster(s) gerado(s) com sucesso."))
        except Exception as exc:
            self.log(f"Erro: {exc}")
            self.root.after(0, lambda: messagebox.showerror("Erro", str(exc)))
        finally:
            self.root.after(0, lambda: self.generate_button.config(state=tk.NORMAL))


def main() -> None:
    root = tk.Tk()
    app = PosterApp(root)
    if app.theme_names:
        root.mainloop()


if __name__ == "__main__":
    main()
