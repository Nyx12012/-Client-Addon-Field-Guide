import io
import json
import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from tavern_shared import theme as _theme
from tavern_shared.theme import (
    BG, SURF, SURF2, BORDER, AMBER, AMBERDIM, PARCH, MUTED, GREEN, RED, CYAN,
    MONO, _mk_scrollbar,
)
from tavern_shared.paths import _tavern_data_dir

try:
    from . import pack as packlib
except ImportError:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        "fieldguide_pack", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pack.py"))
    packlib = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(packlib)

VERSION = "2.1.0"
KEYWORDS_SHOWN = 60
KEYWORD_MIN_PAGES = 3
ANCHOR_TEXT = "\U0001F9E9 TavernKeeper"
BUTTON_TEXT = "\U0001F4D6 Field Guide"
CHUNK = 200
TABLE_ROWS_SHOWN = 14
SEARCH_DELAY_MS = 160
FONT = ("Segoe UI", 10)
SMALL = ("Segoe UI", 9)
TINY = ("Segoe UI", 8)

_btn = _theme._btn


def _data_dir():
    path = os.path.join(_tavern_data_dir(), "fieldguide")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def _sub_dir(name):
    path = os.path.join(_data_dir(), name)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def _packs_dir():
    return _sub_dir("packs")


def _removed_dir():
    return _sub_dir("removed")


def _settings_path():
    return os.path.join(_data_dir(), "fieldguide.json")


def _load_settings():
    try:
        with io.open(_settings_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_settings(data):
    try:
        path = _settings_path()
        tmp = path + ".tmp"
        with io.open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(data, indent=2, ensure_ascii=False))
        os.replace(tmp, path)
    except Exception:
        pass


def _save_json(data, path):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _measure(widget, font, text):
    try:
        return int(widget.tk.call("font", "measure", font, text))
    except Exception:
        return 7 * len(text)


def _open_path(path, parent):
    try:
        os.startfile(path)
    except Exception:
        messagebox.showinfo("Folder", path, parent=parent)


def current_server():
    host, port, name = "", "", ""
    try:
        from client.core.config import load_cfg
        cfg = load_cfg()
        host = str(cfg.get("last_ip", "") or "").strip()
        port = str(cfg.get("last_port", "") or "").strip()
        wanted = host or "127.0.0.1"
        for entry in cfg.get("recent_servers", []) or []:
            if isinstance(entry, dict) and str(entry.get("ip", "")).strip() == wanted:
                name = str(entry.get("name", "") or "").strip()
                break
    except Exception:
        pass
    key = packlib.server_key(host, port or None)
    label = name if name and name != key else key
    if not host:
        label = "%s (this machine)" % label
    return key, label


class Library(object):

    def __init__(self, settings):
        self.settings = settings
        self.packs = []
        self.duplicates = []

    def own_ids(self):
        got = self.settings.get("own_packs")
        ids = set(x for x in got if isinstance(x, str)) if isinstance(got, list) else set()
        ids.add(packlib.NOTES_ID)
        return ids

    def add_own(self, pack_id):
        got = self.settings.get("own_packs")
        ids = [x for x in got if isinstance(x, str)] if isinstance(got, list) else []
        if pack_id not in ids:
            ids.append(pack_id)
        self.settings["own_packs"] = ids
        _save_settings(self.settings)

    def _off(self):
        got = self.settings.get("off")
        return [x for x in got if isinstance(x, str)] if isinstance(got, list) else []

    def is_on(self, loaded):
        return loaded.pack_id not in self._off()

    def set_on(self, loaded, on):
        off = [x for x in self._off() if x != loaded.pack_id]
        if not on:
            off.append(loaded.pack_id)
        self.settings["off"] = off
        _save_settings(self.settings)

    def load(self):
        found = []
        directory = _packs_dir()
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            names = []
        for name in names:
            if not name.lower().endswith(".json") or name.startswith("."):
                continue
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                found.append(packlib.load_file(path))
        own = self.own_ids()
        by_id, self.duplicates = {}, []
        for loaded in found:
            if loaded.pack_id in by_id:
                self.duplicates.append(loaded)
                continue
            by_id[loaded.pack_id] = loaded
            loaded.editable = loaded.pack_id in own and not loaded.fatal
        self.packs = sorted(by_id.values(), key=_pack_order)
        return self.packs

    def readable(self):
        return [p for p in self.packs if not p.fatal]

    def visible(self, server_key=None):
        return [p for p in self.readable()
                if self.is_on(p) and (server_key is None or p.applies_to(server_key))]

    def own_packs(self):
        return [p for p in self.readable() if p.editable]

    def find(self, pack_id):
        for loaded in self.packs:
            if loaded.pack_id == pack_id:
                return loaded
        return None

    def save(self, loaded):
        if not loaded.editable:
            return False
        if not loaded.path:
            loaded.path = os.path.join(_packs_dir(), packlib.file_name_for(loaded.pack_id))
        packlib.save_file(loaded, loaded.path)
        return True

    def install(self, loaded):
        existing = self.find(loaded.pack_id)
        path = existing.path if existing is not None and existing.path else os.path.join(
            _packs_dir(), packlib.file_name_for(loaded.pack_id))
        packlib.save_file(loaded, path)
        return path

    def remove(self, loaded):
        if not loaded.path or not os.path.isfile(loaded.path):
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S")
        base = os.path.splitext(os.path.basename(loaded.path))[0]
        target = os.path.join(_removed_dir(), "%s.%s.json" % (base, stamp))
        os.replace(loaded.path, target)
        return target


def _pack_order(loaded):
    return (loaded.pack_id != packlib.NOTES_ID, packlib.fold(loaded.category) or "~",
            packlib.fold(loaded.title))


def _is_page(payload):
    return isinstance(payload, tuple) and len(payload) == 2 \
        and isinstance(payload[0], packlib.Pack)


def _number(text):
    cleaned = text.replace(",", "").replace("%", "").strip()
    if cleaned.endswith("x"):
        cleaned = cleaned[:-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def _style_once(widget):
    style = ttk.Style(widget)
    style.configure("FGNav.Treeview", background=SURF, fieldbackground=SURF,
                    foreground=PARCH, rowheight=22, borderwidth=0, font=SMALL)
    style.map("FGNav.Treeview", background=[("selected", AMBERDIM)],
              foreground=[("selected", "#ffd080")])
    style.layout("FGNav.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("FGTable.Treeview", background=SURF, fieldbackground=SURF,
                    foreground=PARCH, rowheight=21, borderwidth=0, font=SMALL)
    style.layout("FGTable.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("FGTable.Treeview.Heading", background=SURF2, foreground=AMBER,
                    font=("Segoe UI", 9, "bold"), relief="flat")
    style.map("FGTable.Treeview", background=[("selected", AMBERDIM)],
              foreground=[("selected", "#ffd080")])
    style.map("FGTable.Treeview.Heading", background=[("active", BORDER)])


class FieldGuideWindow(tk.Toplevel):

    def __init__(self, master):
        tk.Toplevel.__init__(self, master)
        self.title("Field Guide")
        self.configure(bg=BG)
        self.geometry("1040x700")
        self.minsize(780, 520)

        self.settings = _load_settings()
        self.library = Library(self.settings)
        self.server_key, self.server_label = current_server()
        self.scope_all = bool(self.settings.get("show_all_servers", False))

        self._nav_items = {}
        self._nav_index = {}
        self._nav_job = None
        self._search_job = None
        self._fit_job = None
        self._history = []
        self._shown = ("home",)
        self._editing = False
        self._dirty = False
        self._autosave_job = None
        self._tables = []
        self._link_targets = {}
        self._packs_window = None

        _style_once(self)
        self._build_ui()
        self.refresh()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            from tavern_shared.window_chrome import _finish_dark_window
            _finish_dark_window(self)
        except Exception:
            pass

    def _build_ui(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(top, text="\U0001F4D6  Field Guide", bg=BG, fg=AMBER,
                 font=("Georgia", 13, "bold")).pack(side="left")
        self.v_scope = tk.StringVar(value="")
        tk.Label(top, textvariable=self.v_scope, bg=BG, fg=MUTED,
                 font=TINY).pack(side="left", padx=(12, 0))
        _btn(top, "Packs", self.open_packs, font=SMALL, pady=4, padx=10).pack(side="right")
        _btn(top, "Import…", self.import_packs, font=SMALL, pady=4,
             padx=10).pack(side="right", padx=(0, 6))
        _btn(top, "New page", self._new_page, font=SMALL, pady=4,
             padx=10).pack(side="right", padx=(0, 6))
        _btn(top, "Home", self._go_home, style="dim", font=SMALL, pady=4,
             padx=10).pack(side="right", padx=(0, 6))

        search_row = tk.Frame(self, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
        search_row.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(search_row, text="  \U0001F50E", bg=SURF, fg=AMBERDIM,
                 font=FONT).pack(side="left")
        self.v_search = tk.StringVar()
        self.v_search.trace_add("write", lambda *_: self._on_search())
        entry = tk.Entry(search_row, textvariable=self.v_search, bg=SURF, fg=PARCH,
                         insertbackground=AMBER, relief="flat", bd=6, font=FONT)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Escape>", lambda _e: self.v_search.set(""))
        entry.bind("<Return>", lambda _e: self._open_first_result())
        self._search_entry = entry

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        left = tk.Frame(body, bg=SURF, highlightbackground=BORDER, highlightthickness=1,
                        width=300)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self.v_count = tk.StringVar(value="")
        tk.Label(left, textvariable=self.v_count, bg=SURF, fg=MUTED, anchor="w",
                 font=TINY).pack(fill="x", padx=8, pady=(6, 2))
        nav_wrap = tk.Frame(left, bg=SURF)
        nav_wrap.pack(fill="both", expand=True, padx=4, pady=(0, 6))
        self.nav = ttk.Treeview(nav_wrap, show="tree", selectmode="browse",
                                style="FGNav.Treeview")
        self.nav.column("#0", width=280, stretch=True)
        nav_scroll = _mk_scrollbar(nav_wrap, self.nav.yview)
        nav_scroll.pack(side="right", fill="y")
        self.nav.pack(side="left", fill="both", expand=True)
        self.nav.config(yscrollcommand=nav_scroll.set)
        self.nav.tag_configure("cat", foreground=AMBER, font=("Georgia", 9, "bold"))
        self.nav.tag_configure("pack", foreground=AMBER)
        self.nav.tag_configure("chapter", foreground=CYAN)
        self.nav.tag_configure("page", foreground=PARCH)
        self.nav.bind("<<TreeviewSelect>>", self._on_nav)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        head = tk.Frame(right, bg=BG)
        head.pack(fill="x")
        self.v_title = tk.StringVar(value="")
        tk.Label(head, textvariable=self.v_title, bg=BG, fg=PARCH, anchor="w",
                 font=("Georgia", 14, "bold")).pack(side="left", fill="x", expand=True)
        self._edit_btn = _btn(head, "Edit", self._toggle_edit, font=SMALL, pady=3, padx=10)
        self._edit_btn.pack(side="right")
        self._delete_btn = _btn(head, "Delete", self._delete_current, style="danger",
                                font=SMALL, pady=3, padx=10)
        self._delete_btn.pack(side="right", padx=(0, 6))
        self._back_btn = _btn(head, "← Back", self._go_back, style="dim", font=SMALL,
                              pady=3, padx=10)
        self._back_btn.pack(side="right", padx=(0, 6))

        self.v_stamp = tk.StringVar(value="")
        self._stamp_label = tk.Label(right, textvariable=self.v_stamp, bg=BG, fg=MUTED,
                                     anchor="w", justify="left", font=TINY)
        self._stamp_label.pack(fill="x", pady=(2, 6))

        text_wrap = tk.Frame(right, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
        text_wrap.pack(fill="both", expand=True)
        self.text = tk.Text(text_wrap, bg=SURF, fg=PARCH, relief="flat", bd=0, wrap="word",
                            padx=14, pady=12, insertbackground=AMBER, font=FONT,
                            highlightthickness=0, spacing1=2, spacing3=4)
        tscroll = _mk_scrollbar(text_wrap, self.text.yview)
        tscroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.config(yscrollcommand=tscroll.set, state="disabled")
        self.text.tag_configure("h", foreground=AMBER, font=("Georgia", 11, "bold"),
                                spacing1=10, spacing3=4)
        self.text.tag_configure("h2", foreground=CYAN, font=("Georgia", 10, "bold"),
                                spacing1=8, spacing3=2)
        self.text.tag_configure("link", foreground=CYAN, underline=True)
        self.text.tag_configure("dim", foreground=MUTED, font=SMALL)
        self.text.tag_configure("note", foreground=MUTED, font=TINY)
        self.text.tag_configure("warn", foreground=RED)
        self.text.tag_configure("ok", foreground=GREEN)
        self.text.tag_configure("mono", font=MONO, foreground=PARCH)
        self.text.tag_bind("link", "<Button-1>", self._on_link_click)
        self.text.tag_bind("link", "<Enter>", lambda _e: self.text.config(cursor="hand2"))
        self.text.tag_bind("link", "<Leave>", lambda _e: self.text.config(cursor=""))
        self.text.bind("<Configure>", lambda _e: self._queue_fit())
        self.bind("<Alt-Left>", lambda _e: self._go_back())

        self.v_status = tk.StringVar(value="")
        tk.Label(self, textvariable=self.v_status, bg=BG, fg=MUTED, anchor="w",
                 font=TINY).pack(fill="x", padx=14, pady=(0, 8))

    def refresh(self):
        self.library.load()
        self._update_scope_label()
        self._rebuild_nav()
        bad = [p for p in self.library.packs if p.fatal] + self.library.duplicates
        total = len(self.library.packs)
        if bad:
            self._status("%d pack%s could not be used. Open Packs to see why."
                         % (len(bad), "" if len(bad) == 1 else "s"))
        else:
            self._status("%d pack%s installed." % (total, "" if total == 1 else "s"))
        self._reshow()
        window = self._packs_window
        if window is not None:
            try:
                if window.winfo_exists():
                    window.render()
            except Exception:
                pass

    def _reshow(self):
        shown = self._shown
        if shown[0] == "page":
            loaded = self.library.find(shown[1].pack_id)
            page = loaded.page_by_id(packlib.page_id(shown[2])) if loaded else None
            if loaded is not None and page is not None and loaded in self._visible_packs():
                self._open(loaded, page, remember=False)
                return
        elif shown[0] == "pack":
            loaded = self.library.find(shown[1].pack_id)
            if loaded is not None and loaded in self._visible_packs():
                self._show_pack(loaded, remember=False)
                return
        self._show_home(remember=False)

    def _visible_packs(self):
        return self.library.visible(None if self.scope_all else self.server_key)

    def _update_scope_label(self):
        on = [p for p in self.library.readable() if self.library.is_on(p)]
        hidden = len(on) - len(self._visible_packs())
        if self.scope_all:
            self.v_scope.set("Showing every pack  ·  server: %s" % self.server_label)
        elif hidden:
            self.v_scope.set("Server: %s  ·  %d pack%s scoped to other servers"
                             % (self.server_label, hidden, "" if hidden == 1 else "s"))
        else:
            self.v_scope.set("Server: %s" % self.server_label)

    def _rebuild_nav(self):
        if self._nav_job is not None:
            try:
                self.after_cancel(self._nav_job)
            except Exception:
                pass
            self._nav_job = None
        self.nav.delete(*self.nav.get_children(""))
        self._nav_items = {}
        self._nav_index = {}
        query = self.v_search.get().strip()
        packs = self._visible_packs()
        ops = []
        counter = [0]

        def make(parent, text, payload, tag, opened=False):
            counter[0] += 1
            iid = "n%d" % counter[0]
            ops.append((parent, iid, text, payload, tag, opened))
            return iid

        if query:
            hits = packlib.search_pages(packs, query)
            for loaded, page in hits:
                make("", "%s   ·   %s" % (packlib.page_title(page), loaded.title),
                     (loaded, page), "page")
            label = "%d page%s matching “%s”" % (
                len(hits), "" if len(hits) == 1 else "s", query)
        else:
            categories = []
            for loaded in packs:
                if loaded.category not in categories:
                    categories.append(loaded.category)
            grouped = len(packs) > 1 and any(categories)
            cat_nodes = {}
            pages = 0
            for loaded in packs:
                parent = ""
                if grouped:
                    name = loaded.category or "Other"
                    if name not in cat_nodes:
                        cat_nodes[name] = make("", name, ("cat", name), "cat", opened=True)
                    parent = cat_nodes[name]
                pack_node = make(parent, loaded.title, loaded, "pack", opened=len(packs) == 1)
                chapter_nodes = {}
                for page in loaded.pages:
                    chapter = packlib.page_chapter(page)
                    holder = pack_node
                    if chapter:
                        if chapter not in chapter_nodes:
                            chapter_nodes[chapter] = make(pack_node, chapter,
                                                          ("chapter", loaded, chapter), "chapter")
                        holder = chapter_nodes[chapter]
                    make(holder, packlib.page_title(page), (loaded, page), "page")
                    pages += 1
            label = "%d page%s in %d pack%s" % (pages, "" if pages == 1 else "s",
                                                len(packs), "" if len(packs) == 1 else "s")
        self.v_count.set(label if ops else ("No matches" if query else "No packs to show"))
        self._fill_nav(ops, 0)

    def _fill_nav(self, ops, start):
        end = min(len(ops), start + CHUNK)
        for parent, iid, text, payload, tag, opened in ops[start:end]:
            self.nav.insert(parent, "end", iid=iid, text="  " + text, open=opened, tags=(tag,))
            self._nav_items[iid] = payload
            if _is_page(payload):
                self._nav_index[(id(payload[0]), id(payload[1]))] = iid
            elif isinstance(payload, packlib.Pack):
                self._nav_index[(id(payload), None)] = iid
        if end < len(ops):
            self._nav_job = self.after(1, lambda: self._fill_nav(ops, end))
            return
        self._nav_job = None
        self._select_in_nav()

    def _select_in_nav(self):
        shown = self._shown
        if shown[0] == "page":
            key = (id(shown[1]), id(shown[2]))
        elif shown[0] == "pack":
            key = (id(shown[1]), None)
        else:
            return
        iid = self._nav_index.get(key)
        if iid is None or not self.nav.exists(iid):
            return
        if tuple(self.nav.selection()) != (iid,):
            self.nav.selection_set(iid)
        self.nav.see(iid)

    def _on_nav(self, _event=None):
        selection = self.nav.selection()
        if not selection:
            return
        payload = self._nav_items.get(selection[0])
        if payload is None:
            return
        if isinstance(payload, packlib.Pack):
            if self._shown[0] == "pack" and self._shown[1] is payload:
                return
            self._show_pack(payload)
        elif _is_page(payload):
            if self._shown[0] == "page" and self._shown[1] is payload[0] \
                    and self._shown[2] is payload[1]:
                return
            self._open(*payload)
        else:
            iid = selection[0]
            self.nav.item(iid, open=not self.nav.item(iid, "open"))

    def _on_search(self):
        if self._editing:
            return
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(SEARCH_DELAY_MS, self._run_search)

    def _run_search(self):
        self._search_job = None
        self._rebuild_nav()

    def _open_first_result(self):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
            self._run_search()
        for iid in self.nav.get_children(""):
            payload = self._nav_items.get(iid)
            if _is_page(payload):
                self._open(*payload)
                return

    def _write(self, chunk, *tags):
        self.text.insert("end", chunk, tags if tags else ())

    def _link(self, target, label=None):
        start = self.text.index("end-1c")
        self._write(target if label is None else label)
        self.text.tag_add("link", start, self.text.index("end-1c"))
        if label is not None:
            self._link_targets[self.text.index(start)] = target

    def _tag_link(self, tag, label=None):
        start = self.text.index("end-1c")
        self._write(label or ("#" + tag))
        self.text.tag_add("link", start, self.text.index("end-1c"))
        self._link_targets[self.text.index(start)] = ("tag", tag)

    def _search_tag(self, tag):
        if self._editing and not self._leave_edit():
            return
        self.v_search.set("#" + tag)
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._run_search()
        self._status("Pages tagged #%s are listed on the left." % tag)

    def _write_body(self, body):
        for kind, value in packlib.split_body(body):
            if kind == "link":
                self._link(value)
            else:
                self._write(value)

    def _begin(self):
        if self._editing:
            self._editing = False
            self.text.unbind("<KeyRelease>")
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        for frame in self._tables:
            try:
                frame[0].destroy()
            except Exception:
                pass
        self._tables = []
        self._link_targets = {}

    def _end(self):
        self.text.config(state="disabled")
        self.text.yview_moveto(0)
        self._queue_fit()

    def _remember(self, remember):
        if remember:
            self._history.append(self._shown)
            del self._history[:-100]

    def _set_header(self, title, stamp="", stamp_ok=True, editable=None):
        self.v_title.set(title)
        self.v_stamp.set(stamp)
        self._stamp_label.config(fg=MUTED if stamp_ok else RED)
        if editable is None:
            self._edit_btn.config(state="disabled", text="Edit")
            self._delete_btn.config(state="disabled")
        else:
            self._edit_btn.config(state="normal",
                                  text="Edit" if editable else "Copy to my notes")
            self._delete_btn.config(state="normal" if editable else "disabled")

    def _go_home(self):
        if self._editing and not self._leave_edit():
            return
        self.v_search.set("")
        self._show_home()

    def _show_home(self, remember=True):
        self._remember(remember and self._shown[0] != "home")
        self._shown = ("home",)
        self._set_header("Field Guide")
        self._begin()
        packs = self._visible_packs()
        if not self.library.packs:
            self._write_welcome()
        elif not packs:
            self._write("No packs to show.\n\n", "warn")
            self._write("Every installed pack is either turned off or scoped to a different "
                        "server than the one the launcher is pointed at. Open Packs to "
                        "change that.\n")
        else:
            self._write("Pick a page on the left, or search. Type # and a keyword to find "
                        "every page with that tag.\n", "dim")
            category = None
            for loaded in packs:
                if loaded.category != category and loaded.category:
                    category = loaded.category
                    self._write("\n" + category.upper() + "\n", "note")
                self._write_card(loaded)
            self._write_keywords(packs)
        self._end()
        if self.nav.selection():
            self.nav.selection_remove(self.nav.selection())

    def _write_welcome(self):
        self._write("Welcome\n", "h")
        self._write("The Field Guide is a reference book for A Township Tale that you fill "
                    "with packs. A pack is one file someone made: a guide to cooking, a "
                    "table of every metal, notes for one server. Packs are plain data. "
                    "Opening one can never run anything on your computer.\n\n")
        self._write("Adding packs\n", "h2")
        self._write("Click Import and pick one or more pack files. A bundle file that "
                    "holds many packs works the same way. Turn packs on and off any time "
                    "in Packs.\n\n")
        self._write("Writing your own\n", "h2")
        self._write("Click New page. Pages you write go into My Notes. To share them, "
                    "make a pack of your own in Packs and export it.\n\n")
        row = tk.Frame(self.text, bg=SURF)
        _btn(row, "Import packs…", self.import_packs, style="primary", font=SMALL,
             pady=4, padx=12).pack(side="left")
        _btn(row, "Open packs folder", lambda: _open_path(_packs_dir(), self), font=SMALL,
             pady=4, padx=12).pack(side="left", padx=(8, 0))
        self.text.window_create("end", window=row)
        self._tables.append((row, None, 0, []))
        self._write("\n")

    def _write_keywords(self, packs):
        counts = [c for c in packlib.tag_counts(packs) if c[1] >= KEYWORD_MIN_PAGES]
        if not counts:
            return
        self._write("\nKEYWORDS\n", "note")
        shown = counts[:KEYWORDS_SHOWN]
        for index, (tag, count) in enumerate(shown):
            if index:
                self._write("  ")
            self._tag_link(tag, "#%s %d" % (tag, count))
        if len(counts) > len(shown):
            self._write("  ·  %d more, search with #" % (len(counts) - len(shown)), "dim")
        self._write("\n")

    def _write_card(self, loaded):
        start = self.text.index("end-1c")
        self._write(loaded.title)
        self.text.tag_add("link", start, self.text.index("end-1c"))
        self.text.tag_add("h", start, self.text.index("end-1c"))
        self._link_targets[self.text.index(start)] = ("pack", loaded)
        self._write("\n")
        if loaded.description:
            self._write(loaded.description + "\n")
        credit = loaded.credit_line()
        if credit:
            self._write(credit + "\n", "dim")
        self._write(loaded.stamp_line() + "\n", "ok" if loaded.verified_against else "warn")
        titles = [packlib.page_title(p) for p in loaded.pages]
        first = []
        if loaded.home and loaded.page_by_title(loaded.home) is not None:
            first.append(loaded.page_by_title(loaded.home))
        for page in loaded.pages:
            if len(first) >= 8:
                break
            if page not in first:
                first.append(page)
        if first:
            for index, page in enumerate(first):
                if index:
                    self._write("  ·  ", "dim")
                self._link(packlib.page_title(page))
            if len(titles) > len(first):
                self._write("  ·  %d more" % (len(titles) - len(first)), "dim")
            self._write("\n")

    def _show_pack(self, loaded, remember=True):
        if self._editing and not self._leave_edit():
            return
        self._remember(remember)
        self._shown = ("pack", loaded)
        credit = loaded.credit_line()
        self._set_header(loaded.title, "%s%s" % (loaded.stamp_line(),
                                                  ("  ·  " + credit) if credit else ""),
                         bool(loaded.verified_against))
        self._begin()
        if loaded.description:
            self._write(loaded.description + "\n\n")
        if loaded.attribution:
            self._write("Text from: %s\n" % loaded.attribution, "dim")
        if loaded.license_url:
            self._write("Licence: %s\n" % loaded.license_url, "dim")
        if loaded.attribution or loaded.license_url:
            self._write("\n")
        if loaded.home and loaded.page_by_title(loaded.home) is not None:
            self._write("Start here: ", "dim")
            self._link(packlib.page_title(loaded.page_by_title(loaded.home)))
            self._write("\n")
        for chapter in loaded.chapters():
            pages = [p for p in loaded.pages if packlib.page_chapter(p) == chapter]
            self._write((chapter or "Pages") + "\n", "h")
            for index, page in enumerate(pages):
                if index:
                    self._write("  ·  ", "dim")
                self._link(packlib.page_title(page))
            self._write("\n")
        if not loaded.pages:
            self._write("This pack has no pages yet.\n", "dim")
        self._end()
        self._select_in_nav()

    def _open(self, loaded, page, remember=True):
        if self._editing and not self._leave_edit():
            return
        self._remember(remember)
        self._shown = ("page", loaded, page)
        credit = loaded.credit_line()
        self._set_header(packlib.page_title(page),
                         "%s  ·  %s%s" % (loaded.title, loaded.stamp_line(),
                                               ("  ·  " + credit) if credit else ""),
                         bool(loaded.verified_against), loaded.editable)
        self._begin()
        chapter = packlib.page_chapter(page)
        tags = packlib.page_tags(page)
        if chapter:
            self._write(chapter, "dim")
        for tag in tags:
            self._write("  ")
            self._tag_link(tag)
        if chapter or tags:
            self._write("\n\n")
        sections = packlib.page_sections(page)
        if not sections:
            self._write("This page has no sections.\n", "dim")
        for section in sections:
            heading = packlib.section_heading(section)
            if heading:
                self._write(heading + "\n", "h")
            body = packlib.section_body(section)
            clipped = len(body) > packlib.MAX_BODY_CHARS
            if body.strip():
                self._write_body(body[:packlib.MAX_BODY_CHARS])
                self._write("\n")
            if clipped:
                self._write("[cut short, this section is over the %d character limit]\n"
                            % packlib.MAX_BODY_CHARS, "warn")
            table = packlib.section_table(section)
            if table:
                self._insert_table(table)
                if table["note"]:
                    self._write(table["note"] + "\n", "note")
            self._write("\n")
        self._end()
        self._select_in_nav()

    def _insert_table(self, table):
        columns, rows = table["columns"], table["rows"]
        frame = tk.Frame(self.text, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
        names = ["c%d" % i for i in range(len(columns))]
        shown = max(1, min(len(rows), TABLE_ROWS_SHOWN))
        tree = ttk.Treeview(frame, columns=names, show="headings", height=shown,
                            selectmode="browse", style="FGTable.Treeview")
        tree.tag_configure("odd", background=SURF2)
        body_font = ("Segoe UI", 9)
        head_font = ("Segoe UI", 9, "bold")
        widths = []
        for index, name in enumerate(columns):
            sample = [packlib.plain(row[index]) for row in rows[:300]]
            natural = max([_measure(tree, head_font, name)] +
                          [_measure(tree, body_font, s) for s in sample])
            widths.append(max(48, min(natural + 22, 460)))
        for index, name in enumerate(names):
            tree.heading(name, text=columns[index],
                         command=lambda i=index: self._sort_table(tree, rows, i))
            tree.column(name, width=widths[index], minwidth=40, stretch=False, anchor="w")
        self._fill_table(tree, rows)
        if len(rows) > shown:
            scroll = _mk_scrollbar(frame, tree.yview)
            scroll.pack(side="right", fill="y")
            tree.config(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        tree.bind("<Double-Button-1>", lambda e: self._table_follow(tree, rows, e))
        tree.bind("<MouseWheel>", lambda e: self._wheel(tree, e, len(rows) > shown))
        tree._fg_sort = None
        self.text.window_create("end", window=frame, padx=0, pady=4)
        self._write("\n")
        self._tables.append((frame, tree, sum(widths), widths))

    def _fill_table(self, tree, rows):
        tree.delete(*tree.get_children(""))
        for index, row in enumerate(rows):
            tree.insert("", "end", iid=str(index), values=[packlib.plain(c) for c in row],
                        tags=("odd",) if index % 2 else ())

    def _wheel(self, tree, event, scrolls):
        if scrolls:
            tree.yview_scroll(int(-event.delta / 120), "units")
        else:
            self.text.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _sort_table(self, tree, rows, index):
        previous = getattr(tree, "_fg_sort", None)
        descending = previous == (index, False)
        values = [packlib.plain(row[index]) for row in rows]
        numbers = [_number(v) for v in values if v.strip()]
        numeric = bool(numbers) and all(n is not None for n in numbers)

        def key(position):
            value = values[position]
            if numeric:
                return _number(value)
            return packlib.fold(value)

        filled = [i for i in range(len(rows)) if values[i].strip()]
        empty = [i for i in range(len(rows)) if not values[i].strip()]
        order = sorted(filled, key=key, reverse=descending) + empty
        for place, position in enumerate(order):
            tree.move(str(position), "", place)
            tree.item(str(position), tags=("odd",) if place % 2 else ())
        tree._fg_sort = (index, descending)

    def _table_follow(self, tree, rows, event):
        iid = tree.identify_row(event.y)
        if not iid:
            return
        row = rows[int(iid)]
        for cell in row:
            links = packlib.page_links(cell)
            if links:
                self._follow(links[0])
                return
        if row:
            self._follow(packlib.plain(row[0]), quiet=True)

    def _queue_fit(self):
        if self._fit_job is not None:
            try:
                self.after_cancel(self._fit_job)
            except Exception:
                pass
        self._fit_job = self.after(60, self._fit_tables)

    def _fit_tables(self):
        self._fit_job = None
        room = self.text.winfo_width() - 2 * 14 - 12
        if room < 120:
            return
        for frame, tree, natural, widths in self._tables:
            if tree is None or not widths:
                continue
            scale = 1.0 if natural <= room else float(room) / natural
            try:
                for index, width in enumerate(widths):
                    tree.column("c%d" % index, width=max(40, int(width * scale)))
            except Exception:
                pass

    def _on_link_click(self, event):
        if self._editing:
            return
        index = self.text.index("@%d,%d" % (event.x, event.y))
        span = self.text.tag_prevrange("link", index + "+1c")
        if not span:
            return
        target = self._link_targets.get(self.text.index(span[0]))
        if isinstance(target, tuple) and target[0] == "pack":
            self._show_pack(target[1])
            return
        if isinstance(target, tuple) and target[0] == "tag":
            self._search_tag(target[1])
            return
        self._follow(target if isinstance(target, str) else self.text.get(*span))

    def _follow(self, target, quiet=False):
        packs = self._visible_packs()
        here = self._shown[1] if self._shown[0] in ("page", "pack") else None
        ordered = ([here] if here in packs else []) + [p for p in packs if p is not here]
        for loaded in ordered:
            page = loaded.page_by_title(target)
            if page is not None:
                self._open(loaded, page)
                return
        if not quiet:
            self._status("No page called “%s” in the packs you can see. A link to a "
                         "page nobody has written yet is a gap, not an error." % target)

    def _go_back(self):
        if self._editing and not self._leave_edit():
            return
        while self._history:
            shown = self._history.pop()
            if shown[0] == "home":
                break
            loaded = self.library.find(shown[1].pack_id)
            if loaded is None or loaded not in self._visible_packs():
                continue
            if shown[0] == "pack":
                self._show_pack(loaded, remember=False)
                return
            page = loaded.page_by_id(packlib.page_id(shown[2]))
            if page is not None:
                self._open(loaded, page, remember=False)
                return
        self._show_home(remember=False)

    def _toggle_edit(self):
        if self._shown[0] != "page":
            return
        loaded, page = self._shown[1], self._shown[2]
        if not loaded.editable:
            self._copy_to_notes(loaded, page)
            return
        if self._editing:
            self._leave_edit()
            return
        self._begin()
        self._editing = True
        self._edit_btn.config(text="Done")
        self.text.insert("1.0", page_as_text(page))
        self.text.config(state="normal")
        self.text.bind("<KeyRelease>", self._on_key)
        self.text.focus_set()
        self._status("Editing. A line “# Heading” starts a section, “@chapter Name” "
                     "and “@tags a, b” go at the top, and “[table]” keeps a table "
                     "where it is. Saves as you type.")

    def _on_key(self, _event=None):
        self._dirty = True
        if self._autosave_job is not None:
            try:
                self.after_cancel(self._autosave_job)
            except Exception:
                pass
        self._autosave_job = self.after(900, self._autosave)

    def _autosave(self):
        self._autosave_job = None
        if not (self._editing and self._dirty and self._shown[0] == "page"):
            return
        loaded, page = self._shown[1], self._shown[2]
        apply_text_to_page(page, self.text.get("1.0", "end-1c"))
        try:
            self.library.save(loaded)
        except OSError as exc:
            self._status("Could not save: %s" % exc)
            return
        self._dirty = False
        self._status("Saved %s  ·  %s" % (loaded.title, time.strftime("%H:%M:%S")))

    def _leave_edit(self):
        if not self._editing:
            return True
        if self._autosave_job is not None:
            try:
                self.after_cancel(self._autosave_job)
            except Exception:
                pass
            self._autosave_job = None
        loaded, page = self._shown[1], self._shown[2]
        apply_text_to_page(page, self.text.get("1.0", "end-1c"))
        try:
            self.library.save(loaded)
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)
            return False
        self._dirty = False
        self._editing = False
        self.text.unbind("<KeyRelease>")
        self._rebuild_nav()
        self._open(loaded, page, remember=False)
        return True

    def _pick_own_pack(self, prompt):
        here = self._shown[1] if self._shown[0] in ("page", "pack") else None
        if here is not None and here.editable:
            return here
        own = self.library.own_packs()
        if len(own) > 1:
            choice = _ask_choice(self, "Which pack?", prompt, [p.title for p in own])
            return None if choice is None else own[choice]
        return self._notes_pack()

    def _new_page(self):
        if self._editing and not self._leave_edit():
            return
        target = self._pick_own_pack("Add the new page to which of your packs?")
        if target is None:
            return
        title = _ask_line(self, "New page", "Title for the new page:")
        if not title:
            return
        if target.page_by_title(title) is not None:
            messagebox.showinfo("Already there", "“%s” already has a page called "
                                "“%s”." % (target.title, title), parent=self)
            return
        page = packlib.new_page(title, [{"heading": "", "body": ""}])
        target.data.setdefault("pages", []).append(page)
        self.library.save(target)
        self._rebuild_nav()
        self._open(target, page)
        self._toggle_edit()

    def _copy_to_notes(self, loaded, page):
        target = self._pick_own_pack("Copy this page into which of your packs?")
        if target is None:
            return
        title = packlib.page_title(page)
        while target.page_by_title(title) is not None:
            title += " (copy)"
        copied = json.loads(json.dumps(page))
        copied["title"] = title
        copied["id"] = packlib.slug(title)
        target.data.setdefault("pages", []).append(copied)
        self.library.save(target)
        self._rebuild_nav()
        self._open(target, copied)
        self._status("Copied into %s. The original is untouched." % target.title)

    def _notes_pack(self):
        found = self.library.find(packlib.NOTES_ID)
        if found is not None and not found.fatal:
            found.editable = True
            return found
        made = packlib.new_pack("My Notes", pack_id=packlib.NOTES_ID)
        made.data["description"] = "Pages you wrote."
        made.data["version"] = ""
        made.path = os.path.join(_packs_dir(), "my-notes.json")
        if os.path.exists(made.path):
            made.path = os.path.join(_packs_dir(), packlib.file_name_for(packlib.NOTES_ID))
        try:
            packlib.save_file(made, made.path)
        except OSError as exc:
            messagebox.showerror("Could not create My Notes", "Writing to %s failed:\n\n%s"
                                 % (_packs_dir(), exc), parent=self)
            return None
        self.library.load()
        return self.library.find(packlib.NOTES_ID)

    def _delete_current(self):
        if self._shown[0] != "page":
            return
        if self._editing and not self._leave_edit():
            return
        loaded, page = self._shown[1], self._shown[2]
        if not loaded.editable:
            return
        if not messagebox.askyesno("Delete page", "Delete “%s” from %s?\n\nThis "
                                   "cannot be undone." % (packlib.page_title(page),
                                                          loaded.title),
                                   icon="warning", parent=self):
            return
        try:
            loaded.data.get("pages", []).remove(page)
        except ValueError:
            return
        self.library.save(loaded)
        self._rebuild_nav()
        self._show_pack(loaded, remember=False)

    def import_packs(self, parent=None):
        parent = parent or self
        paths = filedialog.askopenfilenames(
            title="Import Field Guide packs", parent=parent,
            filetypes=[("Field Guide packs and bundles", "*.json"), ("All files", "*.*")])
        if not paths:
            return
        incoming, errors = [], []
        for path in paths:
            packs, problems = packlib.read_any(path)
            incoming.extend(packs)
            errors.extend("%s: %s" % (os.path.basename(path), p) for p in problems)
        seen, unique = set(), []
        for loaded in incoming:
            if loaded.pack_id in seen:
                errors.append("%s appears more than once; the first copy is used."
                              % loaded.pack_id)
                continue
            seen.add(loaded.pack_id)
            unique.append(loaded)
        if not unique:
            messagebox.showerror("Nothing to import", "\n\n".join(errors[:10]) or
                                 "No packs in what you picked.", parent=parent)
            return
        lines = []
        for loaded in unique:
            existing = self.library.find(loaded.pack_id)
            note = ""
            if existing is not None:
                note = "  (replaces the installed %s)" % (
                    ("version " + existing.version) if existing.version else "copy")
            lines.append("  · %s, %d page%s%s" % (loaded.title, len(loaded.pages),
                                                     "" if len(loaded.pages) == 1 else "s",
                                                     note))
        summary = "Install %d pack%s?\n\n%s" % (len(unique), "" if len(unique) == 1 else "s",
                                               "\n".join(lines[:20]))
        if len(lines) > 20:
            summary += "\n  · and %d more" % (len(lines) - 20)
        if errors:
            summary += "\n\nSkipped:\n" + "\n".join("  · " + e for e in errors[:8])
        if not messagebox.askyesno("Import packs", summary, parent=parent):
            return
        failed = []
        for loaded in unique:
            try:
                self.library.install(loaded)
                self.library.set_on(loaded, True)
            except OSError as exc:
                failed.append("%s: %s" % (loaded.title, exc))
        self.refresh()
        if failed:
            messagebox.showerror("Some packs could not be written", "\n".join(failed),
                                 parent=parent)
        self._status("Imported %d pack%s." % (len(unique) - len(failed),
                                              "" if len(unique) - len(failed) == 1 else "s"))

    def export_pack(self, loaded, parent=None):
        parent = parent or self
        path = filedialog.asksaveasfilename(
            title="Export %s" % loaded.title, parent=parent, defaultextension=".json",
            initialfile=packlib.file_name_for(loaded.pack_id),
            filetypes=[("Field Guide pack", "*.json")])
        if not path:
            return
        try:
            packlib.save_file(loaded, path)
        except OSError as exc:
            messagebox.showerror("Could not export", str(exc), parent=parent)
            return
        self._status("Exported %s." % loaded.title)

    def export_bundle(self, parent=None):
        parent = parent or self
        packs = [p for p in self.library.readable() if self.library.is_on(p)]
        if not packs:
            messagebox.showinfo("Nothing to export", "No packs are turned on.", parent=parent)
            return
        path = filedialog.asksaveasfilename(
            title="Export %d packs as one bundle" % len(packs), parent=parent,
            defaultextension=".json", initialfile="field-guide-bundle.json",
            filetypes=[("Field Guide bundle", "*.json")])
        if not path:
            return
        try:
            _save_json(packlib.bundle(packs, "Field Guide bundle"), path)
        except OSError as exc:
            messagebox.showerror("Could not export", str(exc), parent=parent)
            return
        self._status("Exported %d packs as one bundle." % len(packs))

    def open_packs(self):
        window = self._packs_window
        try:
            if window is not None and window.winfo_exists():
                window.deiconify()
                window.lift()
                return
        except Exception:
            pass
        self._packs_window = PacksWindow(self)

    def _status(self, text):
        self.v_status.set(text)

    def _on_close(self):
        if self._editing:
            self._leave_edit()
        self.settings["show_all_servers"] = self.scope_all
        _save_settings(self.settings)
        self.destroy()


def page_as_text(page):
    out = []
    chapter = packlib.page_chapter(page)
    if chapter:
        out.append("@chapter " + chapter)
    tags = packlib.page_tags(page)
    if tags:
        out.append("@tags " + ", ".join(tags))
    if out:
        out.append("")
    for section in packlib.page_sections(page):
        heading = packlib.section_heading(section)
        if heading:
            out.append("# " + heading)
        body = packlib.section_body(section)
        if body:
            out.append(body)
        if isinstance(section.get("table"), dict):
            out.append("[table]")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def apply_text_to_page(page, text):
    tables = [s.get("table") for s in packlib.page_sections(page)
              if isinstance(s.get("table"), dict)]
    sections = []
    current = {"heading": "", "body": []}
    chapter, tags, header = None, None, True

    def flush():
        body = "\n".join(current["body"]).strip("\n")
        if current["heading"] or body.strip() or "table" in current:
            section = {"heading": current["heading"], "body": body}
            if "table" in current:
                section["table"] = current["table"]
            sections.append(section)

    for line in text.splitlines():
        stripped = line.strip()
        if header and stripped.startswith("@chapter"):
            chapter = stripped[len("@chapter"):].strip()
            continue
        if header and stripped.startswith("@tags"):
            tags = [t.strip() for t in stripped[len("@tags"):].split(",") if t.strip()]
            continue
        if stripped:
            header = False
        if line.startswith("# "):
            flush()
            current = {"heading": line[2:].strip(), "body": []}
        elif stripped == "[table]" and tables:
            if "table" in current:
                flush()
                current = {"heading": "", "body": []}
            current["table"] = tables.pop(0)
        else:
            current["body"].append(line)
    flush()
    page["sections"] = sections
    if chapter is not None:
        if chapter:
            page["chapter"] = chapter
        else:
            page.pop("chapter", None)
    elif "chapter" in page:
        page.pop("chapter", None)
    page["tags"] = tags or []


class PacksWindow(tk.Toplevel):

    def __init__(self, guide):
        tk.Toplevel.__init__(self, guide)
        self.guide = guide
        self.title("Field Guide packs")
        self.configure(bg=BG)
        self.geometry("760x600")
        self.minsize(600, 420)
        self._widgets = []
        self._build()
        try:
            from tavern_shared.window_chrome import _finish_dark_window
            _finish_dark_window(self)
        except Exception:
            pass

    def _build(self):
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(head, text="Packs", bg=BG, fg=AMBER, font=("Georgia", 12, "bold")
                 ).pack(side="left")
        tk.Label(head, text="Field Guide %s" % VERSION, bg=BG, fg=MUTED, font=TINY
                 ).pack(side="left", padx=(10, 0))
        self.v_scope = tk.BooleanVar(value=self.guide.scope_all)
        tk.Checkbutton(head, text="Show packs scoped to other servers", variable=self.v_scope,
                       command=self._toggle_scope, bg=BG, fg=PARCH, selectcolor=SURF,
                       activebackground=BG, activeforeground=AMBER, font=SMALL,
                       highlightthickness=0, bd=0).pack(side="right")

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=12, pady=(2, 8))
        _btn(row, "Import…", lambda: self.guide.import_packs(self), style="primary",
             font=SMALL, pady=4, padx=10).pack(side="left")
        _btn(row, "New pack…", self._new_pack, font=SMALL, pady=4, padx=10
             ).pack(side="left", padx=(6, 0))
        _btn(row, "Export bundle…", lambda: self.guide.export_bundle(self), font=SMALL,
             pady=4, padx=10).pack(side="left", padx=(6, 0))
        _btn(row, "Open packs folder", lambda: _open_path(_packs_dir(), self), font=SMALL,
             pady=4, padx=10).pack(side="left", padx=(6, 0))
        _btn(row, "Reload", self.guide.refresh, style="dim", font=SMALL, pady=4, padx=10
             ).pack(side="right")

        wrap = tk.Frame(self, bg=SURF, highlightbackground=BORDER, highlightthickness=1)
        wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.text = tk.Text(wrap, bg=SURF, fg=PARCH, relief="flat", bd=0, wrap="word",
                            padx=14, pady=12, font=SMALL, highlightthickness=0, cursor="arrow")
        scroll = _mk_scrollbar(wrap, self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.config(yscrollcommand=scroll.set, state="disabled")
        self.text.tag_configure("h", foreground=AMBER, font=("Georgia", 11, "bold"),
                                spacing1=10)
        self.text.tag_configure("off", foreground=MUTED, font=("Georgia", 11, "bold"),
                                spacing1=10)
        self.text.tag_configure("dim", foreground=MUTED)
        self.text.tag_configure("warn", foreground=RED)
        self.text.tag_configure("ok", foreground=GREEN)
        self.text.tag_configure("mono", font=MONO, foreground=MUTED)
        self.render()

    def render(self):
        library = self.guide.library
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        for widget in self._widgets:
            try:
                widget.destroy()
            except Exception:
                pass
        self._widgets = []

        def write(chunk, *tags):
            self.text.insert("end", chunk, tags if tags else ())

        write("Server the launcher is pointed at: %s\n" % self.guide.server_label, "dim")
        if not library.packs:
            write("\nNo packs installed yet. Click Import to add some.\n", "warn")

        for loaded in library.packs:
            if loaded.fatal:
                write("%s\n" % os.path.basename(loaded.path or "?"), "h")
                write("Could not be read:\n", "warn")
                for problem in loaded.problems:
                    if problem.fatal:
                        write("   · %s\n" % problem.line(), "warn")
                self._buttons(loaded, broken=True)
                write("\n\n")
                continue
            on = library.is_on(loaded)
            write(loaded.title + "\n", "h" if on else "off")
            self._buttons(loaded)
            write("\n")
            if loaded.description:
                write(loaded.description + "\n")
            write("%s\n" % (loaded.credit_line() or "No author or licence given."),
                  "dim" if loaded.credit_line() else "warn")
            if loaded.attribution:
                write("Text from: %s\n" % loaded.attribution, "dim")
            if loaded.license_url:
                write("%s\n" % loaded.license_url, "dim")
            write("%s\n" % loaded.stamp_line(), "ok" if loaded.verified_against else "warn")
            write("%d page%s  ·  %s  ·  servers: %s%s\n"
                  % (len(loaded.pages), "" if len(loaded.pages) == 1 else "s",
                     loaded.category or "no category", ", ".join(loaded.servers),
                     "  ·  yours, editable" if loaded.editable else ""), "dim")
            if not on:
                write("Turned off: hidden from the guide.\n", "dim")
            elif not loaded.applies_to(self.guide.server_key) and not self.guide.scope_all:
                write("Hidden: scoped to a different server.\n", "dim")
            source = loaded.source
            if source.get("generated_by"):
                write("Generated by %s%s\n" % (source["generated_by"],
                                               (" from " + str(source["from"]))
                                               if source.get("from") else ""), "dim")
            warnings = [p for p in loaded.problems if not p.fatal]
            if warnings:
                write("Worth knowing:\n", "dim")
                for problem in warnings[:8]:
                    write("   · %s\n" % problem.line(), "dim")
                if len(warnings) > 8:
                    write("   · and %d more\n" % (len(warnings) - 8), "dim")
            write("%s\n\n" % (loaded.path or ""), "mono")

        for loaded in library.duplicates:
            write("%s\n" % os.path.basename(loaded.path or "?"), "off")
            write("Not used: another file already has the id %s.\n" % loaded.pack_id, "warn")
            self._buttons(loaded, broken=True)
            write("\n\n")
        self.text.config(state="disabled")

    def _buttons(self, loaded, broken=False):
        row = tk.Frame(self.text, bg=SURF)
        if not broken:
            on = self.guide.library.is_on(loaded)
            _btn(row, "Turn off" if on else "Turn on", lambda: self._toggle(loaded),
                 style="dim" if on else "success", font=TINY, pady=2, padx=8
                 ).pack(side="left")
            _btn(row, "Export…", lambda: self.guide.export_pack(loaded, self), font=TINY,
                 pady=2, padx=8).pack(side="left", padx=(6, 0))
            if loaded.editable:
                _btn(row, "Details…", lambda: self._details(loaded), font=TINY, pady=2,
                     padx=8).pack(side="left", padx=(6, 0))
        if loaded.pack_id != packlib.NOTES_ID or broken:
            _btn(row, "Remove", lambda: self._remove(loaded), style="danger", font=TINY,
                 pady=2, padx=8).pack(side="left", padx=(6, 0))
        self.text.window_create("end", window=row)
        self._widgets.append(row)

    def _toggle(self, loaded):
        self.guide.library.set_on(loaded, not self.guide.library.is_on(loaded))
        self.guide.refresh()

    def _toggle_scope(self):
        self.guide.scope_all = bool(self.v_scope.get())
        self.guide.refresh()

    def _remove(self, loaded):
        name = loaded.title if not loaded.fatal else os.path.basename(loaded.path or "")
        if not messagebox.askyesno("Remove pack", "Remove %s?\n\nThe file is moved to the "
                                   "“removed” folder next to your packs, so it can be "
                                   "put back by hand." % name, icon="warning", parent=self):
            return
        try:
            self.guide.library.remove(loaded)
        except OSError as exc:
            messagebox.showerror("Could not remove", str(exc), parent=self)
            return
        self.guide.refresh()

    def _new_pack(self):
        values = _ask_form(self, "New pack", PACK_FIELDS, {"version": "1.0.0", "servers": "*"})
        if not values or not values.get("title"):
            return
        made = packlib.new_pack(values["title"], author=values.get("author", ""))
        if self.guide.library.find(made.pack_id) is not None:
            made.data["id"] = "%s-%s" % (made.pack_id, time.strftime("%Y%m%d%H%M%S"))
        _apply_form(made, values)
        made.path = os.path.join(_packs_dir(), packlib.file_name_for(made.pack_id))
        try:
            packlib.save_file(made, made.path)
        except OSError as exc:
            messagebox.showerror("Could not create the pack", str(exc), parent=self)
            return
        self.guide.library.add_own(made.pack_id)
        self.guide.refresh()

    def _details(self, loaded):
        current = {
            "title": loaded.title, "description": loaded.description,
            "author": loaded.author, "license": loaded.license,
            "category": loaded.category, "version": loaded.version,
            "verified_against": loaded.verified_against, "verified_on": loaded.verified_on,
            "servers": ", ".join(loaded.servers),
        }
        values = _ask_form(self, "Pack details", PACK_FIELDS, current)
        if not values:
            return
        _apply_form(loaded, values)
        try:
            self.guide.library.save(loaded)
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)
            return
        self.guide.refresh()


PACK_FIELDS = (
    ("title", "Title"),
    ("description", "Description"),
    ("author", "Author"),
    ("license", "Licence (for example CC0-1.0 or CC-BY-4.0)"),
    ("category", "Category (for example Players, Crafting, Developers)"),
    ("version", "Version"),
    ("verified_against", "Game build it was checked against"),
    ("verified_on", "Date it was checked"),
    ("servers", "Servers it is for (* for every server, or host names with commas)"),
)


def _apply_form(loaded, values):
    for key, _label in PACK_FIELDS:
        if key == "servers":
            loaded.set_servers([h.strip() for h in values.get("servers", "*").split(",")])
        elif key == "title":
            if values.get("title"):
                loaded.data["title"] = values["title"]
        else:
            loaded.data[key] = values.get(key, "")


def _dress(dialog, parent):
    dialog.configure(bg=BG)
    dialog.transient(parent)
    dialog.resizable(False, False)
    try:
        from tavern_shared.window_chrome import _finish_dark_window
        _finish_dark_window(dialog)
    except Exception:
        pass


def _dialog_buttons(dialog, ok):
    row = tk.Frame(dialog, bg=BG)
    row.pack(fill="x", padx=18, pady=14)
    _btn(row, "Cancel", dialog.destroy, style="dim", font=SMALL, pady=4, padx=12
         ).pack(side="right")
    _btn(row, "OK", ok, style="primary", font=SMALL, pady=4, padx=16
         ).pack(side="right", padx=(0, 6))


def _ask_line(parent, title, prompt, initial=""):
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    _dress(dialog, parent)
    tk.Label(dialog, text=prompt, bg=BG, fg=PARCH, font=FONT).pack(padx=18, pady=(16, 6),
                                                                  anchor="w")
    var = tk.StringVar(value=initial)
    entry = tk.Entry(dialog, textvariable=var, bg=SURF, fg=PARCH, width=44,
                     insertbackground=AMBER, relief="flat", bd=6, font=FONT)
    entry.pack(padx=18, fill="x")
    entry.focus_set()
    out = {"value": None}

    def ok(_event=None):
        out["value"] = var.get().strip()
        dialog.destroy()

    _dialog_buttons(dialog, ok)
    entry.bind("<Return>", ok)
    entry.bind("<Escape>", lambda _e: dialog.destroy())
    dialog.grab_set()
    parent.wait_window(dialog)
    return out["value"] or None


def _ask_form(parent, title, fields, initial):
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    _dress(dialog, parent)
    holder = tk.Frame(dialog, bg=BG)
    holder.pack(fill="x", padx=18, pady=(12, 0))
    vars_ = {}
    first = None
    for key, label in fields:
        tk.Label(holder, text=label, bg=BG, fg=MUTED, font=TINY, anchor="w"
                 ).pack(fill="x", pady=(6, 1))
        var = tk.StringVar(value=initial.get(key, ""))
        entry = tk.Entry(holder, textvariable=var, bg=SURF, fg=PARCH, width=56,
                         insertbackground=AMBER, relief="flat", bd=5, font=SMALL)
        entry.pack(fill="x")
        vars_[key] = var
        first = first or entry
    out = {"value": None}

    def ok(_event=None):
        out["value"] = dict((k, v.get().strip()) for k, v in vars_.items())
        dialog.destroy()

    _dialog_buttons(dialog, ok)
    dialog.bind("<Return>", ok)
    dialog.bind("<Escape>", lambda _e: dialog.destroy())
    if first is not None:
        first.focus_set()
    dialog.grab_set()
    parent.wait_window(dialog)
    return out["value"]


def _ask_choice(parent, title, prompt, options):
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    _dress(dialog, parent)
    tk.Label(dialog, text=prompt, bg=BG, fg=PARCH, font=FONT).pack(padx=18, pady=(16, 6),
                                                                  anchor="w")
    box = tk.Listbox(dialog, bg=SURF, fg=PARCH, selectbackground=AMBERDIM,
                     selectforeground="#ffd080", relief="flat", bd=0, highlightthickness=0,
                     activestyle="none", height=min(12, len(options)), font=SMALL, width=46)
    for option in options:
        box.insert("end", "  " + option)
    box.selection_set(0)
    box.pack(padx=18, fill="x")
    out = {"value": None}

    def ok(_event=None):
        selection = box.curselection()
        out["value"] = selection[0] if selection else None
        dialog.destroy()

    _dialog_buttons(dialog, ok)
    box.bind("<Double-Button-1>", ok)
    dialog.grab_set()
    parent.wait_window(dialog)
    return out["value"]


_armed = {"first": False, "button": False}
_window = {"it": None}


def _text_of(widget):
    try:
        return str(widget.cget("text"))
    except Exception:
        return ""


def _walk(widget, seen=None):
    if seen is None:
        seen = set()
    key = str(widget)
    if key in seen:
        return
    seen.add(key)
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        children = []
    for child in children:
        for found in _walk(child, seen):
            yield found


def _squash(text):
    return "".join(char for char in text.lower() if char.isalnum())


def _find_anchor(root):
    for widget in _walk(root):
        if _text_of(widget) == ANCHOR_TEXT:
            return widget
    for widget in _walk(root):
        try:
            if widget.winfo_class() != "Button":
                continue
        except Exception:
            continue
        if "tavernkeeper" in _squash(_text_of(widget)):
            return widget
    return None


def _has_button(parent):
    try:
        return any(_text_of(child) == BUTTON_TEXT for child in parent.winfo_children())
    except Exception:
        return False


def open_guide(root):
    existing = _window["it"]
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return existing
        except Exception:
            pass
    _window["it"] = FieldGuideWindow(root)
    return _window["it"]


def _inject_button(root):
    if _armed["button"]:
        return
    anchor = _find_anchor(root)
    if anchor is None:
        return
    try:
        if _has_button(anchor.master):
            _armed["button"] = True
            return
        button = _theme._btn(anchor.master, BUTTON_TEXT, lambda: open_guide(root),
                             font=SMALL, pady=5, padx=10)
        button.pack(side="left", padx=(6, 0))
        _armed["button"] = True
    except Exception:
        pass


def _first_arm(root):
    if _armed["first"]:
        return
    _armed["first"] = True
    _inject_button(root)


def _lazy_arm():
    root = getattr(tk, "_default_root", None)
    if root is None or _armed["first"]:
        return
    try:
        root.after_idle(lambda: _first_arm(root))
    except Exception:
        pass


def _wrap(orig):
    def _fieldguide_btn(parent, text, cmd, style="normal", **kw):
        button = orig(parent, text, cmd, style, **kw)
        _lazy_arm()
        return button
    return _fieldguide_btn


_theme._btn = _wrap(_theme._btn)

for _name in ("client.core.launcher_window", "tavern_shared.addon_manager_window"):
    _module = sys.modules.get(_name)
    if _module is not None and callable(getattr(_module, "_btn", None)):
        _module._btn = _wrap(_module._btn)
