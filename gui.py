import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import create_map_poster as poster
from map_poster.theme_management import get_available_themes, load_theme


class PosterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("City Map Poster Generator")
        self.root.geometry("860x820")
        self.root.minsize(780, 720)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.theme_names = get_available_themes()
        if not self.theme_names:
            messagebox.showerror("Erro", "Nenhum tema encontrado em themes/.")
            self.root.destroy()
            return

        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root)
        outer.grid(row=0, column=0, sticky=tk.NSEW)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)

        main = ttk.Frame(self.canvas, padding=12)
        self._canvas_window = self.canvas.create_window((0, 0), window=main, anchor=tk.NW)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)
        main.bind("<Configure>", self._update_scrollregion)
        self.canvas.bind("<Configure>", self._update_canvas_width)
        self._bind_mousewheel(self.canvas)

        form = ttk.LabelFrame(main, text="Configurações", padding=12)
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

        options = ttk.Frame(form)
        options.grid(row=11, column=0, columnspan=2, sticky=tk.W, pady=8)
        ttk.Checkbutton(options, text="Gerar todos os temas", variable=self.all_themes_var).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(options, text="Atualizar cache", variable=self.refresh_cache_var).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Button(options, text="Listar temas", command=self.show_themes).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Button(options, text="Salvar configuração", command=self.save_config).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Button(options, text="Carregar configuração", command=self.load_config).pack(side=tk.LEFT)

        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(main, padding=(0, 12, 0, 12))
        actions.grid(row=1, column=0, sticky=tk.EW)
        self.generate_button = ttk.Button(actions, text="Gerar pôster", command=self.start_generation)
        self.generate_button.pack(side=tk.RIGHT)

        layers_frame = ttk.LabelFrame(main, text="Camadas OSMnx", padding=8)
        layers_frame.grid(row=2, column=0, sticky=tk.EW)
        layers_frame.columnconfigure(0, weight=1)
        layers_frame.columnconfigure(1, weight=1)
        for index, (key, label, default) in enumerate(self.layer_options):
            var = tk.BooleanVar(value=default)
            self.layer_vars[key] = var
            column = index % 2
            row = index // 2
            ttk.Checkbutton(layers_frame, text=label, variable=var).grid(row=row, column=column, sticky=tk.W)

        log_frame = ttk.LabelFrame(main, text="Logs", padding=8)
        log_frame.grid(row=3, column=0, sticky=tk.NSEW)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(log_frame, height=12, state=tk.DISABLED)
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

    def _parse_coordinates(self, value: str) -> tuple[float, float]:
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 2:
            raise ValueError("Informe coordenadas no formato: lat, lon.")
        try:
            lat = float(parts[0])
            lon = float(parts[1])
        except ValueError as exc:
            raise ValueError("Coordenadas inválidas. Use números decimais.") from exc
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Coordenadas fora do intervalo permitido.")
        return (lat, lon)

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
            "enabled_layers": enabled_layers,
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

        enabled_layers = config.get("enabled_layers")
        if isinstance(enabled_layers, list):
            enabled_set = {layer for layer in enabled_layers if isinstance(layer, str)}
            for key, _, _ in self.layer_options:
                self.layer_vars[key].set(key in enabled_set)
        self.log(f"Configuração carregada de: {file_path}")
        messagebox.showinfo("Configuração carregada", "Configuração carregada com sucesso.")

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

            themes_to_generate = self.theme_names if self.all_themes_var.get() else [self.theme_var.get()]
            self.log(f"Temas selecionados: {', '.join(themes_to_generate)}")
            selected_layers = [key for key, _, _ in self.layer_options if self.layer_vars[key].get()]
            selected_labels = [label for key, label, _ in self.layer_options if self.layer_vars[key].get()]
            if selected_labels:
                self.log(f"Camadas OSMnx: {', '.join(selected_labels)}")
            else:
                self.log("Camadas OSMnx: nenhuma")
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
                    enabled_layers=selected_layers,
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
