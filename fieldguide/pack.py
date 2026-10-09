import io
import json
import os
import re
import unicodedata

FORMAT = "tavern-fieldguide-pack"
BUNDLE_FORMAT = "tavern-fieldguide-bundle"
FORMAT_VERSION = 2

MAX_PACK_BYTES = 8 * 1024 * 1024
MAX_BUNDLE_BYTES = 48 * 1024 * 1024
MAX_BUNDLE_PACKS = 200
MAX_PAGES = 5000
MAX_SECTIONS_PER_PAGE = 500
MAX_BODY_CHARS = 200000
MAX_TITLE_CHARS = 200
MAX_TABLE_ROWS = 5000
MAX_TABLE_COLUMNS = 40
MAX_CELL_CHARS = 2000

ANY_SERVER = "*"
DEFAULT_GAME_PORT = "1757"
NOTES_ID = "local.my-notes"

SHARE_ALIKE_HINTS = ("by-sa", "sharealike", "share-alike", "gfdl")


class PackProblem(object):

    __slots__ = ("text", "fatal", "where")

    def __init__(self, text, fatal=False, where=""):
        self.text = text
        self.fatal = bool(fatal)
        self.where = where

    def __repr__(self):
        return "PackProblem(%r, fatal=%r, where=%r)" % (self.text, self.fatal, self.where)

    def line(self):
        return ("%s: %s" % (self.where, self.text)) if self.where else self.text


class Pack(object):

    def __init__(self, data, path=None, problems=None, editable=False):
        self.data = data if isinstance(data, dict) else {}
        self.path = path
        self.problems = list(problems or ())
        self.editable = bool(editable)

    @property
    def pack_id(self):
        got = _as_text(self.data.get("id")).strip()
        if got:
            return got
        return "untitled." + slug(self.title or (os.path.basename(self.path or "") or "pack"))

    @property
    def title(self):
        return _as_text(self.data.get("title")).strip() or "Untitled pack"

    @property
    def author(self):
        return _as_text(self.data.get("author")).strip()

    @property
    def license(self):
        return _as_text(self.data.get("license")).strip()

    @property
    def license_url(self):
        return _as_text(self.data.get("license_url")).strip()

    @property
    def attribution(self):
        return _as_text(self.data.get("attribution")).strip()

    @property
    def description(self):
        return _as_text(self.data.get("description")).strip()

    @property
    def category(self):
        return _as_text(self.data.get("category")).strip()

    @property
    def version(self):
        return _as_text(self.data.get("version")).strip()

    @property
    def home(self):
        return _as_text(self.data.get("home")).strip()

    @property
    def fatal(self):
        return any(problem.fatal for problem in self.problems)

    @property
    def verified_against(self):
        return _as_text(self.data.get("verified_against")).strip()

    @property
    def verified_on(self):
        return _as_text(self.data.get("verified_on")).strip()

    @property
    def source(self):
        got = self.data.get("source")
        return got if isinstance(got, dict) else {}

    def stamp_line(self):
        build = self.verified_against
        when = self.verified_on
        if build and when:
            return "Verified against %s on %s" % (build, when)
        if build:
            return "Verified against %s" % build
        if when:
            return "Checked %s, game build not recorded" % when
        return "Not verified against any game version"

    def credit_line(self):
        bits = []
        if self.author:
            bits.append("by %s" % self.author)
        if self.license:
            bits.append(self.license)
        if self.version:
            bits.append("version %s" % self.version)
        return "  ·  ".join(bits)

    @property
    def servers(self):
        raw = self.data.get("servers")
        if raw is None:
            return [ANY_SERVER]
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return [ANY_SERVER]
        out = [server_key(item) for item in raw if _as_text(item).strip()]
        return out or [ANY_SERVER]

    def set_servers(self, hosts):
        cleaned = [server_key(h) for h in hosts if _as_text(h).strip()]
        self.data["servers"] = cleaned or [ANY_SERVER]

    def applies_to(self, key):
        entries = self.servers
        if ANY_SERVER in entries:
            return True
        return server_key(key) in entries

    @property
    def pages(self):
        raw = self.data.get("pages")
        return [p for p in raw if isinstance(p, dict)] if isinstance(raw, list) else []

    def page_by_title(self, title):
        want = fold(title)
        for page in self.pages:
            if fold(page_title(page)) == want:
                return page
        return None

    def page_by_id(self, wanted):
        for page in self.pages:
            if page_id(page) == wanted:
                return page
        return None

    def chapters(self):
        seen = []
        for page in self.pages:
            name = page_chapter(page)
            if name not in seen:
                seen.append(name)
        return seen


def page_title(page):
    return _as_text(page.get("title")).strip() or "Untitled page"


def page_id(page):
    return _as_text(page.get("id")).strip() or slug(page_title(page))


def page_chapter(page):
    return _as_text(page.get("chapter")).strip()


def page_tags(page):
    raw = page.get("tags")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [_as_text(t).strip() for t in raw if _as_text(t).strip()]


def page_sections(page):
    raw = page.get("sections")
    if not isinstance(raw, list):
        return []
    return [s for s in raw[:MAX_SECTIONS_PER_PAGE] if isinstance(s, dict)]


def section_heading(section):
    return _as_text(section.get("heading")).strip()


def section_body(section):
    return _as_text(section.get("body"))


def section_table(section):
    raw = section.get("table")
    if not isinstance(raw, dict):
        return None
    columns = raw.get("columns")
    rows = raw.get("rows")
    if not isinstance(columns, list) or not columns:
        return None
    if not isinstance(rows, list):
        rows = []
    columns = [cell_text(c) for c in columns[:MAX_TABLE_COLUMNS]]
    width = len(columns)
    out = []
    for row in rows[:MAX_TABLE_ROWS]:
        if not isinstance(row, list):
            continue
        cells = [cell_text(c) for c in row[:width]]
        cells.extend([""] * (width - len(cells)))
        out.append(cells)
    return {"columns": columns, "rows": out, "note": _as_text(raw.get("note")).strip()}


def cell_text(value):
    text = _as_text(value)
    if len(text) > MAX_CELL_CHARS:
        text = text[:MAX_CELL_CHARS - 1] + "…"
    return text


def plain(text):
    return LINK_RE.sub(lambda m: m.group(1).strip(), text or "")


def page_text(page):
    parts = [page_title(page), page_chapter(page)]
    parts.extend(page_tags(page))
    for section in page_sections(page):
        parts.append(section_heading(section))
        parts.append(plain(section_body(section)))
        table = section_table(section)
        if table:
            parts.append(" ".join(table["columns"]))
            for row in table["rows"]:
                parts.append(plain(" ".join(row)))
            parts.append(table["note"])
    return "\n".join(p for p in parts if p)


LINK_RE = re.compile(r"\[\[([^\[\]\r\n]{1,%d})\]\]" % MAX_TITLE_CHARS)


def page_links(body):
    seen = []
    lowered = set()
    for match in LINK_RE.finditer(body or ""):
        target = match.group(1).strip()
        if not target:
            continue
        key = fold(target)
        if key in lowered:
            continue
        lowered.add(key)
        seen.append(target)
    return seen


def page_all_links(page):
    out = []
    for section in page_sections(page):
        out.extend(page_links(section_body(section)))
        table = section_table(section)
        if table:
            for row in table["rows"]:
                for cell in row:
                    out.extend(page_links(cell))
    seen = set()
    unique = []
    for target in out:
        if fold(target) not in seen:
            seen.add(fold(target))
            unique.append(target)
    return unique


def split_body(body):
    out = []
    pos = 0
    text = body or ""
    for match in LINK_RE.finditer(text):
        if match.start() > pos:
            out.append(("text", text[pos:match.start()]))
        target = match.group(1).strip()
        if target:
            out.append(("link", target))
        else:
            out.append(("text", match.group(0)))
        pos = match.end()
    if pos < len(text):
        out.append(("text", text[pos:]))
    return out


def server_key(host, port=None):
    text = _as_text(host).strip().lower()
    if text == ANY_SERVER:
        return ANY_SERVER
    if not text:
        text = "127.0.0.1"
    if ":" in text and port is None:
        text, _, found = text.rpartition(":")
        port = found
    port = _as_text(port).strip()
    if port and port != DEFAULT_GAME_PORT:
        return "%s:%s" % (text, port)
    return text


def problems_for(data):
    out = []

    if not isinstance(data, dict):
        return [PackProblem(
            "The file is valid JSON but it is a %s, not a pack. A pack is a "
            "single JSON object with a \"pages\" list." % type(data).__name__,
            fatal=True)]

    fmt = _as_text(data.get("format"))
    if fmt == BUNDLE_FORMAT:
        return [PackProblem("This is a bundle of packs, not a single pack. Import it "
                            "and each pack inside is installed on its own.", fatal=True)]
    if fmt and fmt != FORMAT:
        return [PackProblem(
            "This file says it is a \"%s\", which is not a Field Guide pack." % fmt,
            fatal=True)]
    if not fmt:
        out.append(PackProblem("No \"format\" field. Loading it as a Field Guide pack anyway."))

    version = data.get("format_version")
    if isinstance(version, bool) or not isinstance(version, int):
        if version is not None:
            out.append(PackProblem(
                "\"format_version\" should be a whole number; got %r." % (version,)))
    elif version > FORMAT_VERSION:
        out.append(PackProblem(
            "Written for pack format %d; this Field Guide reads format %d. Parts it "
            "does not know are shown as they are and saved back untouched."
            % (version, FORMAT_VERSION)))

    raw_pages = data.get("pages")
    if raw_pages is None:
        return out + [PackProblem("No \"pages\" list, so there is nothing to read.",
                                  fatal=True)]
    if not isinstance(raw_pages, list):
        return out + [PackProblem(
            "\"pages\" is a %s; it has to be a list of pages." % type(raw_pages).__name__,
            fatal=True)]
    if len(raw_pages) > MAX_PAGES:
        return out + [PackProblem(
            "%d pages, over the %d page limit. Refusing to load it rather than "
            "locking the window up." % (len(raw_pages), MAX_PAGES), fatal=True)]

    skipped = sum(1 for p in raw_pages if not isinstance(p, dict))
    if skipped:
        out.append(PackProblem(
            "%d entr%s in \"pages\" %s not a page and will be ignored."
            % (skipped, "y" if skipped == 1 else "ies", "is" if skipped == 1 else "are")))

    seen_titles = {}
    for index, page in enumerate(raw_pages):
        if not isinstance(page, dict):
            continue
        out.extend(_page_problems(page, index, seen_titles))

    out.extend(_licence_problems(data))
    if not _as_text(data.get("verified_against")).strip():
        out.append(PackProblem(
            "No \"verified_against\" stamp, so there is no way to tell how old this "
            "pack's answers are. It will be shown as unverified."))
    return out


def _page_problems(page, index, seen_titles):
    out = []
    where = "page %d" % (index + 1)
    title = page_title(page)
    if len(title) > MAX_TITLE_CHARS:
        out.append(PackProblem("Title is %d characters, over the %d character limit."
                               % (len(title), MAX_TITLE_CHARS), where=where))
    folded = fold(title)
    if folded in seen_titles:
        out.append(PackProblem(
            "Another page is also called \"%s\" (page %d). Links go by title, so "
            "they will all land on the first one." % (title, seen_titles[folded] + 1),
            where=where))
    else:
        seen_titles[folded] = index

    raw_sections = page.get("sections")
    if raw_sections is None:
        out.append(PackProblem("No sections, so this page will show empty.", where=where))
        return out
    if not isinstance(raw_sections, list):
        out.append(PackProblem("\"sections\" is a %s; it has to be a list. This page "
                               "will show empty." % type(raw_sections).__name__,
                               where=where))
        return out
    if len(raw_sections) > MAX_SECTIONS_PER_PAGE:
        out.append(PackProblem("%d sections, over the %d section limit. The rest will "
                               "be ignored." % (len(raw_sections), MAX_SECTIONS_PER_PAGE),
                               where=where))
    for s_index, section in enumerate(raw_sections[:MAX_SECTIONS_PER_PAGE]):
        if not isinstance(section, dict):
            out.append(PackProblem("Section %d is a %s, not a section, and will be ignored."
                                   % (s_index + 1, type(section).__name__), where=where))
            continue
        body = section_body(section)
        if len(body) > MAX_BODY_CHARS:
            out.append(PackProblem("Section %d is %d characters, over the %d character "
                                   "limit, and will be shown cut short."
                                   % (s_index + 1, len(body), MAX_BODY_CHARS), where=where))
        if "table" in section:
            out.extend(_table_problems(section.get("table"), s_index, where))
    return out


def _table_problems(raw, s_index, where):
    label = "Section %d's table" % (s_index + 1)
    if not isinstance(raw, dict):
        return [PackProblem("%s is a %s, not a table, and will not be shown."
                            % (label, type(raw).__name__), where=where)]
    columns = raw.get("columns")
    if not isinstance(columns, list) or not columns:
        return [PackProblem("%s has no \"columns\" list and will not be shown." % label,
                            where=where)]
    out = []
    if len(columns) > MAX_TABLE_COLUMNS:
        out.append(PackProblem("%s has %d columns; only the first %d are shown."
                               % (label, len(columns), MAX_TABLE_COLUMNS), where=where))
    rows = raw.get("rows")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        return out + [PackProblem("%s has \"rows\" as a %s; it has to be a list."
                                  % (label, type(rows).__name__), where=where)]
    if len(rows) > MAX_TABLE_ROWS:
        out.append(PackProblem("%s has %d rows; only the first %d are shown."
                               % (label, len(rows), MAX_TABLE_ROWS), where=where))
    width = len(columns)
    odd = sum(1 for row in rows[:MAX_TABLE_ROWS] if not isinstance(row, list) or len(row) != width)
    if odd:
        out.append(PackProblem("%s has %d row%s that do not have %d cells. Short rows are "
                               "padded, long ones cut, and non lists skipped."
                               % (label, odd, "" if odd == 1 else "s", width), where=where))
    return out


def _licence_problems(data):
    out = []
    licence = _as_text(data.get("license")).strip()
    attribution = _as_text(data.get("attribution")).strip()
    author = _as_text(data.get("author")).strip()
    if not licence:
        out.append(PackProblem("No \"license\" field, so it is not clear what may be done "
                               "with this pack's text."))
    else:
        folded = licence.lower().replace(" ", "")
        if any(hint in folded for hint in SHARE_ALIKE_HINTS) and not attribution:
            out.append(PackProblem(
                "The licence is share alike (%s) but there is no \"attribution\" field "
                "saying where the text came from. Share alike licences require credit."
                % licence))
    if not author:
        out.append(PackProblem("No \"author\" field."))
    return out


def _parse(text):
    try:
        return json.loads(text), None
    except ValueError as exc:
        return None, "This is not valid JSON, so it cannot be read: %s" % _short(exc)
    except RecursionError:
        return None, "The JSON in this file is nested far too deeply to be a pack."
    except Exception as exc:
        return None, "This file could not be read: %s" % _short(exc)


def load_text(text, path=None, editable=False):
    data, error = _parse(text)
    if error:
        return Pack({}, path=path, editable=editable,
                    problems=[PackProblem(error, fatal=True)])
    return from_data(data, path=path, editable=editable)


def from_data(data, path=None, editable=False):
    return Pack(data if isinstance(data, dict) else {}, path=path, editable=editable,
                problems=problems_for(data))


def _read(path, limit):
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return None, "Could not open this file: %s" % _short(exc)
    if size > limit:
        return None, ("This file is %.1f MB, over the %d MB limit."
                      % (size / 1024.0 / 1024.0, limit // (1024 * 1024)))
    try:
        with io.open(path, "r", encoding="utf-8-sig") as handle:
            return handle.read(), None
    except UnicodeDecodeError:
        return None, ("This file is not UTF-8 text. If it came out of a spreadsheet or "
                      "an old editor, save it again as UTF-8.")
    except OSError as exc:
        return None, "Could not read this file: %s" % _short(exc)


def load_file(path, editable=False):
    text, error = _read(path, MAX_PACK_BYTES)
    if error:
        return Pack({}, path=path, editable=editable,
                    problems=[PackProblem(error, fatal=True)])
    return load_text(text, path=path, editable=editable)


def read_any(path):
    text, error = _read(path, MAX_BUNDLE_BYTES)
    if error:
        return [], [error]
    data, error = _parse(text)
    if error:
        return [], [error]
    if isinstance(data, dict) and _as_text(data.get("format")) == BUNDLE_FORMAT:
        return _unbundle(data)
    if len(text.encode("utf-8")) > MAX_PACK_BYTES:
        return [], ["This pack is over the %d MB limit for a single pack."
                    % (MAX_PACK_BYTES // (1024 * 1024))]
    loaded = from_data(data, path=path)
    if loaded.fatal:
        return [], [p.line() for p in loaded.problems if p.fatal]
    return [loaded], []


def _unbundle(data):
    raw = data.get("packs")
    if not isinstance(raw, list):
        return [], ["This bundle has no \"packs\" list."]
    if len(raw) > MAX_BUNDLE_PACKS:
        return [], ["This bundle holds %d packs, over the %d pack limit."
                    % (len(raw), MAX_BUNDLE_PACKS)]
    packs, errors = [], []
    for index, item in enumerate(raw):
        loaded = from_data(item)
        if loaded.fatal:
            errors.append("Pack %d in the bundle: %s" % (
                index + 1, "; ".join(p.text for p in loaded.problems if p.fatal)))
            continue
        if len(dumps(loaded).encode("utf-8")) > MAX_PACK_BYTES:
            errors.append("Pack %d in the bundle (%s) is over the %d MB limit."
                          % (index + 1, loaded.title, MAX_PACK_BYTES // (1024 * 1024)))
            continue
        packs.append(loaded)
    return packs, errors


def bundle(packs, title=""):
    return {
        "format": BUNDLE_FORMAT,
        "format_version": FORMAT_VERSION,
        "title": title,
        "packs": [p.data if isinstance(p, Pack) else p for p in packs],
    }


def dumps(pack):
    data = pack.data if isinstance(pack, Pack) else pack
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def save_file(pack, path):
    text = dumps(pack)
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, path)
    return path


def file_name_for(pack_id):
    return slug(pack_id, keep_dots=True) + ".json"


def new_pack(title, author="", pack_id=None, license_name="", servers=None):
    data = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "id": pack_id or make_id(author, title),
        "title": title,
        "description": "",
        "category": "",
        "version": "1.0.0",
        "author": author,
        "license": license_name,
        "verified_against": "",
        "verified_on": "",
        "servers": [server_key(h) for h in servers] if servers else [ANY_SERVER],
        "pages": [],
    }
    return Pack(data, editable=True)


def make_id(author, title):
    return "%s.%s" % (slug(author or "local"), slug(title))


def new_page(title, sections=None, chapter=""):
    page = {"id": slug(title), "title": title, "tags": [],
            "sections": list(sections or ())}
    if chapter:
        page["chapter"] = chapter
    return page


def search_pages(packs, query, limit=300):
    needle = fold(query).strip()
    if needle.startswith("#"):
        return tag_pages(packs, needle[1:].strip(), limit)
    if not needle:
        return []
    hits = []
    for pack in packs:
        for page in pack.pages:
            title = page_title(page)
            folded = fold(title)
            if folded == needle:
                rank = 0
            elif folded.startswith(needle):
                rank = 1
            elif needle in folded:
                rank = 2
            elif any(needle in fold(tag) for tag in page_tags(page)):
                rank = 3
            elif needle in fold(page_chapter(page)):
                rank = 4
            elif needle in fold(page_text(page)):
                rank = 5
            else:
                continue
            hits.append((rank, folded, fold(pack.title), pack, page))
    hits.sort(key=lambda item: (item[0], item[1], item[2]))
    return [(pack, page) for _, _, _, pack, page in hits[:limit]]


def tag_key(tag):
    key = " ".join(fold(tag).split())
    if len(key) > 3 and key.endswith("s") and not key.endswith("ss"):
        return key[:-1]
    return key


def tag_pages(packs, tag, limit=300):
    want = tag_key(tag)
    if not want:
        return []
    hits = []
    for pack in packs:
        for page in pack.pages:
            folded = [tag_key(t) for t in page_tags(page)]
            if want in folded:
                rank = 0
            elif any(t.startswith(want) for t in folded):
                rank = 1
            else:
                continue
            hits.append((rank, fold(page_title(page)), fold(pack.title), pack, page))
    hits.sort(key=lambda item: (item[0], item[1], item[2]))
    return [(pack, page) for _, _, _, pack, page in hits[:limit]]


def tag_counts(packs):
    counts = {}
    forms = {}
    for pack in packs:
        for page in pack.pages:
            for key in set(tag_key(t) for t in page_tags(page)):
                counts[key] = counts.get(key, 0) + 1
            for tag in page_tags(page):
                seen = forms.setdefault(tag_key(tag), {})
                seen[tag] = seen.get(tag, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    out = []
    for key, count in ordered:
        name = sorted(forms[key].items(), key=lambda item: (-item[1], item[0]))[0][0]
        out.append((name, count))
    return out


def snippet_for(page, query, width=140):
    needle = fold(query).strip()
    text = " ".join(page_text(page).split())
    if not needle:
        return text[:width]
    where = fold(text).find(needle)
    if where < 0:
        return text[:width]
    start = max(0, where - width // 3)
    piece = text[start:start + width]
    return ("…" + piece) if start else piece


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return ""


def fold(text):
    stripped = unicodedata.normalize("NFKD", _as_text(text))
    return "".join(c for c in stripped if not unicodedata.combining(c)).casefold()


def slug(text, keep_dots=False):
    out = []
    for char in fold(text):
        if char.isalnum() or (keep_dots and char == "."):
            out.append(char)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-.") or "page"


def _short(exc, limit=160):
    text = " ".join(str(exc).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"
