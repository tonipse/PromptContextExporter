#!/usr/bin/env python3
"""
export_code.py – Version 3.1  (14 Jul 2025)

• Nach Basisordnerwahl erscheint ein Tree-Dialog mit Checkboxen.
• Es werden nur die Dateien exportiert, die der Benutzer auch wirklich
  angehakt hat. Versteckte Ordner/Dateien (".git", ".venv", …) bleiben
  außen vor.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --------------------------------------------------------------------------- #
#  Globale Einstellungen                                                      #
# --------------------------------------------------------------------------- #

CODE_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".cs", ".cpp", ".c", ".h", ".hpp",
    ".java", ".kt", ".swift", ".rb", ".php", ".go", ".rs",
}
EXPORT_FILENAME = "export.txt"
ENCODING = "utf-8"

UNCHECKED = "☐"   # U+2610
CHECKED   = "☑"   # U+2611

# Verzeichnisse, die komplett ignoriert werden sollen
IGNORE_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules"}

# --------------------------------------------------------------------------- #
#  Hilfsfunktionen                                                            #
# --------------------------------------------------------------------------- #


def relativize(path: Path, base: Path) -> str:
    try:
        rel = path.relative_to(base)
    except ValueError:
        rel = path
    return rel.as_posix().replace("/", os.sep)


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def collect_code_files_in_dir(directory: Path) -> list[Path]:
    """Alle Code-Dateien unterhalb *sichtbarer* Ordner rekursiv sammeln."""
    return [
        p
        for p in directory.rglob("*")
        if p.is_file()
        and p.suffix.lower() in CODE_EXTENSIONS
        and not any(part.startswith(".") or part in IGNORE_DIRS
                    for part in p.relative_to(directory).parts)
    ]


def read_file(path: Path) -> str:
    with open(path, "r", encoding=ENCODING, errors="replace") as f:
        return normalize_newlines(f.read())


def write_export(base_dir: Path, entries: list[tuple[str, str]]) -> Path:
    out_path = base_dir / EXPORT_FILENAME
    with open(out_path, "w", encoding=ENCODING, newline="\n") as out:
        for rel, code in entries:
            out.write(f'Datei: "{rel}"\n')
            out.write('Code: """\\\n')
            out.write(code)
            out.write('\n"""\n\n')
    return out_path

# --------------------------------------------------------------------------- #
#  Baum-Auswalldialog                                                         #
# --------------------------------------------------------------------------- #


class TreeSelectDialog(tk.Toplevel):
    """Checkbox-Tree für Ordner/Dateien. Liefert (selected_dirs, selected_files)."""

    def __init__(self, master: tk.Widget, base_dir: Path):
        super().__init__(master)
        self.title("Dateien & Ordner auswählen")
        self.geometry("600x500")
        self.minsize(400, 300)

        self.base_dir = base_dir
        self.selected_items: dict[str, bool] = {}    # Tree-ID → checked?
        self.id_to_path: dict[str, Path] = {}        # Tree-ID → Path

        # --- Treeview ------------------------------------------------------
        self.tree = ttk.Treeview(self, show="tree")
        y_scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=y_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")

        self.tree.bind("<Button-1>", self._on_click)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        ttk.Button(btn_frame, text="Alles markieren", command=self._select_all).pack(
            side="left", padx=2
        )
        ttk.Button(btn_frame, text="Nichts markieren", command=self._deselect_all).pack(
            side="left", padx=2
        )
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel).pack(
            side="right", padx=2
        )
        ttk.Button(btn_frame, text="OK", command=self._on_ok).pack(
            side="right", padx=2
        )

        # Baum aufbauen
        self._build_tree()

        # Rückgabewerte
        self.result_dirs: list[Path] | None = None
        self.result_files: list[Path] | None = None

        # Modal machen
        self.lift()
        self.grab_set()
        self.focus_force()
        self.wait_window()

    # --------------------------------------------------------------------- #
    #  Baumaufbau                                                           #
    # --------------------------------------------------------------------- #

    def _build_tree(self):
        def insert_node(parent_id: str, path: Path):
            node_id = self.tree.insert(
                parent_id, "end",
                text=f"{UNCHECKED} {path.name}", open=False
            )
            self.selected_items[node_id] = False
            self.id_to_path[node_id] = path
            if path.is_dir():
                self.tree.insert(node_id, "end")  # Dummy-Child

        root_id = self.tree.insert(
            "", "end",
            text=f"{UNCHECKED} {self.base_dir.name}", open=True
        )
        self.selected_items[root_id] = False
        self.id_to_path[root_id] = self.base_dir

        def on_open(event):
            item = self.tree.focus()
            if self.tree.get_children(item):
                first = self.tree.get_children(item)[0]
                if (
                    self.id_to_path.get(first) is None
                    and not self.tree.get_children(first)
                ):
                    self.tree.delete(first)
                    self.selected_items.pop(first, None)          # Dummy aus Liste
                    path = self.id_to_path[item]
                    for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
                        if (child.name.startswith(".")
                                or child.name in IGNORE_DIRS):
                            continue
                        insert_node(item, child)

        self.tree.bind("<<TreeviewOpen>>", on_open)

        for child in sorted(self.base_dir.iterdir(), key=lambda p: p.name.lower()):
            if not (child.name.startswith(".") or child.name in IGNORE_DIRS):
                insert_node(root_id, child)

    # --------------------------------------------------------------------- #
    #  Checkbox-Handling                                                    #
    # --------------------------------------------------------------------- #

    def _toggle_item(self, item_id: str, new_state: bool | None = None):
        cur = self.selected_items[item_id]
        new_state = (not cur) if new_state is None else new_state
        self._set_item_state(item_id, new_state)

    def _set_item_state(self, item_id: str, state: bool):
        text = self.tree.item(item_id, "text")
        name = text.split(" ", 1)[1] if " " in text else text
        self.tree.item(item_id, text=f"{CHECKED if state else UNCHECKED} {name}")
        self.selected_items[item_id] = state
        for child in self.tree.get_children(item_id):
            self._set_item_state(child, state)

    def _on_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and self.tree.identify("region", event.x, event.y) == "tree":
            if self.tree.identify("element", event.x, event.y) == "text":
                self._toggle_item(iid)

    # --------------------------------------------------------------------- #
    #  Button-Aktionen                                                      #
    # --------------------------------------------------------------------- #

    def _select_all(self):
        for iid in self.selected_items:
            self._set_item_state(iid, True)

    def _deselect_all(self):
        for iid in self.selected_items:
            self._set_item_state(iid, False)

    def _on_ok(self):
        dirs, files = [], []
        for iid, checked in self.selected_items.items():
            if not checked:
                continue
            path = self.id_to_path.get(iid)        # Dummy? → None
            if path is None:
                continue
            (dirs if path.is_dir() else files).append(path)
        self.result_dirs, self.result_files = dirs, files
        self.destroy()

    def _on_cancel(self):
        self.destroy()

# --------------------------------------------------------------------------- #
#  Hauptprogramm                                                              #
# --------------------------------------------------------------------------- #


def run_selection_dialog(root: tk.Tk, base: Path):
    dlg = TreeSelectDialog(root, base)
    if dlg.result_dirs is None:          # Abbruch
        return None
    return dlg.result_dirs, dlg.result_files


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    folder = filedialog.askdirectory(
        title="Basisordner auswählen",
        parent=root
    )
    if not folder:
        root.destroy()
        sys.exit("Abbruch: kein Basisordner gewählt.")

    base_dir = Path(folder).resolve()

    sel = run_selection_dialog(root, base_dir)
    if sel is None:
        root.destroy()
        sys.exit("Abbruch durch Benutzer.")

    sel_dirs, sel_files = sel
    if not sel_dirs and not sel_files:
        root.destroy()
        sys.exit("Keine Ordner/Dateien ausgewählt.")

    files_to_export: set[Path] = set()

    # Rekursiv nur sichtbar-/ausgewählte Ordner
    for d in sel_dirs:
        files_to_export.update(collect_code_files_in_dir(d))

    # Einzeldateien
    for f in sel_files:
        if f.suffix.lower() in CODE_EXTENSIONS:
            files_to_export.add(f)

    if not files_to_export:
        root.destroy()
        sys.exit("Keine passenden Code-Dateien gefunden.")

    entries = [
        (relativize(p, base_dir), read_file(p)) for p in sorted(files_to_export)
    ]
    out_path = write_export(base_dir, entries)

    messagebox.showinfo(
        "Export abgeschlossen",
        f"exportiert: {len(files_to_export)} Dateien\n\n"
        f"Datei wurde erzeugt:\n{out_path}",
        parent=root
    )
    root.destroy()
    print(f"✅  {len(files_to_export)} Dateien exportiert → {out_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbbruch.")
