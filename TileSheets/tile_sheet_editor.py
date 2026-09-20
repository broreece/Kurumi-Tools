from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk
except ImportError as exc:
    raise SystemExit(
        "Pillow is required. Install with: pip install Pillow"
    ) from exc


@dataclass
class TileData:
    tile_id: int
    art_id: int
    passable: bool = False
    pathway: bool = False
    see_through: bool = False


def sql_bool(value: bool) -> str:
    return "TRUE" if value else "FALSE"


# (passable, see_through, pathway) → overlay fill
FLAG_COLORS = {
    (False, False, False): "#e53935",  # red
    (True, False, False): "#43a047",  # green
    (False, True, False): "#fdd835",  # yellow
    (False, False, True): "#1e88e5",  # blue
    (True, True, False): "#00bcd4",  # cyan
    (True, False, True): "#8e24aa",  # purple
    (False, True, True): "#fb8c00",  # orange
    (True, True, True): "#ffffff",  # white
}

ZOOM_MIN = 0.25
ZOOM_MAX = 16.0
ZOOM_STEP = 1.25


class TileSheetEditorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Tile Sheet Editor")
        self.root.minsize(720, 520)

        self.pil_image: Image.Image | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.image_path: str | None = None
        self.tiles: dict[tuple[int, int], TileData] = {}
        self.selected: tuple[int, int] | None = None
        self.grid_cols = 0
        self.grid_rows = 0
        self.zoom = 1.0

        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill=tk.X)

        ttk.Button(toolbar, text="Open PNG…", command=self.load_image).pack(
            side=tk.LEFT, padx=(0, 8)
        )

        ttk.Label(toolbar, text="Tile width:").pack(side=tk.LEFT)
        self.tile_w_var = tk.StringVar(value="16")
        ttk.Entry(toolbar, textvariable=self.tile_w_var, width=6).pack(
            side=tk.LEFT, padx=(4, 12)
        )

        ttk.Label(toolbar, text="Tile height:").pack(side=tk.LEFT)
        self.tile_h_var = tk.StringVar(value="16")
        ttk.Entry(toolbar, textvariable=self.tile_h_var, width=6).pack(
            side=tk.LEFT, padx=(4, 12)
        )

        ttk.Button(toolbar, text="Apply grid", command=self.apply_grid).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(toolbar, text="Upload (SQL)", command=self.generate_sql).pack(
            side=tk.LEFT, padx=(0, 16)
        )

        ttk.Button(toolbar, text="−", width=3, command=lambda: self.adjust_zoom(1 / ZOOM_STEP)).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="+", width=3, command=lambda: self.adjust_zoom(ZOOM_STEP)).pack(
            side=tk.LEFT, padx=(4, 8)
        )
        self.zoom_label = ttk.Label(toolbar, text="100%")
        self.zoom_label.pack(side=tk.LEFT)

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        canvas_frame = ttk.Frame(body)
        body.add(canvas_frame, weight=3)

        self.canvas = tk.Canvas(canvas_frame, background="#2b2b2b", highlightthickness=0)
        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        h_scroll.grid(row=1, column=0, sticky="ew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-4>", self.on_mousewheel)
        self.canvas.bind("<Button-5>", self.on_mousewheel)
        self.root.bind("<Control-plus>", lambda _e: self.adjust_zoom(ZOOM_STEP))
        self.root.bind("<Control-equal>", lambda _e: self.adjust_zoom(ZOOM_STEP))
        self.root.bind("<Control-minus>", lambda _e: self.adjust_zoom(1 / ZOOM_STEP))
        self.root.bind("<Control-0>", lambda _e: self.set_zoom(1.0))

        side = ttk.Frame(body, padding=8)
        body.add(side, weight=1)

        ttk.Label(side, text="Selected tile", font=("", 10, "bold")).pack(anchor=tk.W)
        self.selection_label = ttk.Label(side, text="(none)")
        self.selection_label.pack(anchor=tk.W, pady=(0, 8))

        self.passable_var = tk.BooleanVar(value=False)
        self.pathway_var = tk.BooleanVar(value=False)
        self.see_through_var = tk.BooleanVar(value=False)

        for text, var in (
            ("passable", self.passable_var),
            ("pathway", self.pathway_var),
            ("see_through", self.see_through_var),
        ):
            ttk.Checkbutton(
                side,
                text=text,
                variable=var,
                command=self.sync_flags_from_ui,
            ).pack(anchor=tk.W)

        self.status_var = tk.StringVar(value="Open a PNG and apply a grid.")
        ttk.Label(self.root, textvariable=self.status_var, padding=(8, 4)).pack(
            fill=tk.X
        )

    def load_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Select tile sheet PNG",
            filetypes=[("PNG images", "*.png"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            img = Image.open(path).convert("RGBA")
        except OSError as exc:
            messagebox.showerror("Load failed", str(exc))
            return

        self.pil_image = img
        self.image_path = path
        self.tiles.clear()
        self.selected = None
        self.zoom = 1.0
        self._update_zoom_label()
        self._refresh_canvas_image()
        self.status_var.set(f"Loaded {path} ({img.width}×{img.height})")
        self.apply_grid()

    def _parse_tile_size(self) -> tuple[int, int] | None:
        try:
            tw = int(self.tile_w_var.get().strip())
            th = int(self.tile_h_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid size", "Tile width and height must be integers.")
            return None
        if tw <= 0 or th <= 0:
            messagebox.showerror("Invalid size", "Tile width and height must be positive.")
            return None
        return tw, th

    def apply_grid(self) -> None:
        if self.pil_image is None:
            messagebox.showinfo("No image", "Open a PNG image first.")
            return
        sizes = self._parse_tile_size()
        if sizes is None:
            return
        tw, th = sizes
        w, h = self.pil_image.size
        self.grid_cols = w // tw
        self.grid_rows = h // th
        if self.grid_cols == 0 or self.grid_rows == 0:
            messagebox.showerror(
                "Grid too large",
                "Tile size is larger than the image; no tiles fit.",
            )
            return

        new_tiles: dict[tuple[int, int], TileData] = {}
        tile_id = 1
        for row in range(self.grid_rows):
            for col in range(self.grid_cols):
                key = (col, row)
                existing = self.tiles.get(key)
                if existing:
                    existing.tile_id = tile_id
                    existing.art_id = tile_id
                    new_tiles[key] = existing
                else:
                    new_tiles[key] = TileData(
                        tile_id=tile_id,
                        art_id=tile_id,
                    )
                tile_id += 1
        self.tiles = new_tiles
        self.draw_grid()
        self.status_var.set(
            f"Grid: {self.grid_cols}×{self.grid_rows} tiles ({len(self.tiles)} total)"
        )

    def _bind_mousewheel(self, _event: tk.Event | None = None) -> None:
        self.canvas.focus_set()
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind_all("<Button-4>", self.on_mousewheel)
        self.canvas.bind_all("<Button-5>", self.on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event | None = None) -> None:
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _cell_size(self) -> tuple[int, int] | None:
        sizes = self._parse_tile_size()
        if sizes is None:
            return None
        tw, th = sizes
        return max(1, int(tw * self.zoom)), max(1, int(th * self.zoom))

    def _update_zoom_label(self) -> None:
        self.zoom_label.configure(text=f"{int(round(self.zoom * 100))}%")

    def set_zoom(self, zoom: float, anchor: tuple[float, float] | None = None) -> None:
        if self.pil_image is None:
            return
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        if abs(new_zoom - self.zoom) < 1e-6:
            return

        if anchor is None:
            canvas_x = self.canvas.canvasx(self.canvas.winfo_width() / 2)
            canvas_y = self.canvas.canvasy(self.canvas.winfo_height() / 2)
        else:
            canvas_x, canvas_y = anchor

        image_x = canvas_x / self.zoom
        image_y = canvas_y / self.zoom
        self.zoom = new_zoom
        self._update_zoom_label()
        self.draw_grid()

        new_x = image_x * self.zoom
        new_y = image_y * self.zoom
        region = self.canvas.cget("scrollregion").split()
        if len(region) == 4:
            width = float(region[2])
            height = float(region[3])
            view_w = self.canvas.winfo_width()
            view_h = self.canvas.winfo_height()
            if width > view_w:
                self.canvas.xview_moveto(max(0.0, (new_x - view_w / 2) / width))
            if height > view_h:
                self.canvas.yview_moveto(max(0.0, (new_y - view_h / 2) / height))

    def adjust_zoom(self, factor: float, event: tk.Event | None = None) -> None:
        anchor = None
        if event is not None:
            anchor = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self.set_zoom(self.zoom * factor, anchor)

    def on_mousewheel(self, event: tk.Event) -> None:
        delta = getattr(event, "delta", 0)
        num = getattr(event, "num", None)
        zoom_in = delta > 0 or num == 4
        zoom_out = delta < 0 or num == 5
        if zoom_in:
            self.adjust_zoom(ZOOM_STEP, event)
        elif zoom_out:
            self.adjust_zoom(1 / ZOOM_STEP, event)

    def _refresh_canvas_image(self) -> None:
        if self.pil_image is None:
            return
        w = max(1, int(self.pil_image.width * self.zoom))
        h = max(1, int(self.pil_image.height * self.zoom))
        if self.zoom == 1.0:
            display = self.pil_image
        else:
            display = self.pil_image.resize((w, h), Image.Resampling.NEAREST)
        self.photo = ImageTk.PhotoImage(display)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo, tags=("image",))
        self.canvas.configure(scrollregion=(0, 0, w, h))

    def draw_grid(self) -> None:
        if self.pil_image is None:
            return
        self._refresh_canvas_image()
        cell = self._cell_size()
        if cell is None:
            return
        tw, th = cell

        for row in range(self.grid_rows):
            for col in range(self.grid_cols):
                x0 = col * tw
                y0 = row * th
                x1 = x0 + tw
                y1 = y0 + th
                tile = self.tiles[(col, row)]
                fill = self._tile_overlay_color(tile)
                tag = f"tile_{col}_{row}"
                self.canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    fill=fill,
                    stipple="gray50",
                    outline="",
                    tags=(tag, "overlay"),
                )
                self.canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    outline="#666666",
                    width=1,
                    tags=(tag, "grid"),
                )
                if self.selected == (col, row):
                    self.canvas.create_rectangle(
                        x0 + 1,
                        y0 + 1,
                        x1 - 1,
                        y1 - 1,
                        outline="#111111",
                        width=3,
                        tags=(tag, "selection"),
                    )
                self.canvas.create_text(
                    x0 + 4,
                    y0 + 4,
                    anchor=tk.NW,
                    text=str(tile.tile_id),
                    fill="#111111",
                    tags=(tag, "label"),
                )

    def _tile_overlay_color(self, tile: TileData) -> str:
        return FLAG_COLORS[
            (tile.passable, tile.see_through, tile.pathway)
        ]

    def on_canvas_click(self, event: tk.Event) -> None:
        if not self.tiles or self.pil_image is None:
            return
        cell = self._cell_size()
        if cell is None:
            return
        tw, th = cell
        col = int(self.canvas.canvasx(event.x)) // tw
        row = int(self.canvas.canvasy(event.y)) // th
        if col < 0 or row < 0 or col >= self.grid_cols or row >= self.grid_rows:
            return
        self.selected = (col, row)
        tile = self.tiles[(col, row)]
        self.passable_var.set(tile.passable)
        self.pathway_var.set(tile.pathway)
        self.see_through_var.set(tile.see_through)
        self.selection_label.configure(
            text=f"id {tile.tile_id}, art_id {tile.art_id} @ ({col}, {row})"
        )
        self.draw_grid()

    def sync_flags_from_ui(self) -> None:
        if self.selected is None:
            return
        tile = self.tiles[self.selected]
        tile.passable = self.passable_var.get()
        tile.pathway = self.pathway_var.get()
        tile.see_through = self.see_through_var.get()
        self.draw_grid()

    def generate_sql(self) -> None:
        if not self.tiles:
            messagebox.showinfo("No tiles", "Load an image and apply a grid first.")
            return

        ordered = sorted(
            self.tiles.values(),
            key=lambda t: t.tile_id,
        )
        lines = [
            "INSERT INTO tiles (id, art_id, passable, pathway, see_through) VALUES"
        ]
        value_rows = []
        for tile in ordered:
            value_rows.append(
                f"  ({tile.tile_id}, {tile.art_id}, "
                f"{sql_bool(tile.passable)}, {sql_bool(tile.pathway)}, "
                f"{sql_bool(tile.see_through)})"
            )
        lines.append(",\n".join(value_rows) + ";")
        sql = "\n".join(lines)

        win = tk.Toplevel(self.root)
        win.title("SQL INSERT")
        win.geometry("640x480")
        text = tk.Text(win, wrap=tk.NONE, font=("Consolas", 10))
        x_scroll = ttk.Scrollbar(win, orient=tk.HORIZONTAL, command=text.xview)
        y_scroll = ttk.Scrollbar(win, orient=tk.VERTICAL, command=text.yview)
        text.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        text.insert("1.0", sql)
        text.configure(state=tk.DISABLED)

        btn_row = ttk.Frame(win, padding=8)
        btn_row.pack(fill=tk.X, side=tk.BOTTOM)

        def copy_sql() -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(sql)
            self.status_var.set("SQL copied to clipboard.")

        def save_sql() -> None:
            path = filedialog.asksaveasfilename(
                defaultextension=".sql",
                filetypes=[("SQL files", "*.sql"), ("All files", "*.*")],
            )
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(sql)
            self.status_var.set(f"Saved SQL to {path}")

        ttk.Button(btn_row, text="Copy", command=copy_sql).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="Save as…", command=save_sql).pack(side=tk.LEFT)

        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        x_scroll.pack(side=tk.BOTTOM, fill=tk.X)


def main() -> None:
    root = tk.Tk()
    TileSheetEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
