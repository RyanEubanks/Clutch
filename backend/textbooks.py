"""OpenStax textbooks: import their source files, search them, and quiz from them.

OpenStax publishes free textbooks; their source (CNXML, one folder per section) is on
GitHub at github.com/openstax/osbooks-*. Run import_openstax.py to download a book's text
(images are skipped: ~97% of the download) and build a searchable copy here.

Everything lives in its own database file (user_data/textbooks.db), separate from student
data, so it can be deleted and rebuilt any time.

How the app uses a book (all offline):
  - Search: the 2-3 passages that best match a topic or question (SQLite FTS5, ms).
  - Tutor chat: those passages go into the prompt, within DOC_CHAR_BUDGET.
  - Quizzes: the book's own multiple-choice review questions (official answer keys) and
    glossary terms make questions that are right by construction.
  - Notes check: quiz quotes can be checked against the passages, like the student's notes.

Licenses: most OpenStax books are CC BY-NC-SA 4.0; some are CC BY 4.0. The license is
read from each book's own files and shown, with the title and a link, wherever content
from it appears (attribution is required). Nothing from the books is stored in git.
"""
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BACKEND_DIR / "user_data" / "textbooks.db"
SOURCE_DIR = BACKEND_DIR / "user_data" / "openstax"  # downloaded repos (text only)

# Which free OpenStax book(s) go with which catalog course (courses.py ids).
# repo: github.com/openstax/<repo>; slug: the book inside the repo (META-INF/books.xml).
BOOKS = {
    "biology": [("osbooks-biology-bundle", "biology-2e")],
    "chemistry": [("osbooks-chemistry-bundle", "chemistry-2e")],
    "physics": [("osbooks-physics", "physics")],
    "statistics": [("osbooks-introductory-statistics-bundle", "introductory-statistics-2e")],
    "pre-algebra": [("osbooks-prealgebra-bundle", "prealgebra-2e")],
    "algebra-1": [("osbooks-prealgebra-bundle", "elementary-algebra-2e")],
    "algebra-2": [("osbooks-prealgebra-bundle", "intermediate-algebra-2e")],
    "calculus-1": [("osbooks-calculus-bundle", "calculus-volume-1")],
    "us-history": [("osbooks-us-history", "us-history")],
    "world-history": [("osbooks-world-history", "world-history-volume-1"),
                      ("osbooks-world-history", "world-history-volume-2")],
    "civics": [("osbooks-american-government", "american-government-4e")],
    "economics": [("osbooks-principles-economics-bundle", "principles-economics-3e")],
    "psychology": [("osbooks-psychology", "psychology-2e")],
    "computer-science": [("osbooks-introduction-python-programming", "introduction-python-programming")],
}
# Titles, so the app can offer a book before it's downloaded (the real title is read on import).
TITLES = {
    "biology-2e": "Biology 2e",
    "chemistry-2e": "Chemistry 2e",
    "physics": "Physics",
    "introductory-statistics-2e": "Introductory Statistics 2e",
    "prealgebra-2e": "Prealgebra 2e",
    "elementary-algebra-2e": "Elementary Algebra 2e",
    "intermediate-algebra-2e": "Intermediate Algebra 2e",
    "calculus-volume-1": "Calculus Volume 1",
    "us-history": "U.S. History",
    "world-history-volume-1": "World History Volume 1, to 1500",
    "world-history-volume-2": "World History Volume 2, from 1400",
    "american-government-4e": "American Government 4e",
    "principles-economics-3e": "Principles of Economics 3e",
    "psychology-2e": "Psychology 2e",
    "introduction-python-programming": "Introduction to Python Programming",
}
REPO_URL = "https://github.com/openstax/{repo}.git"
PASSAGE_CHARS = 900  # passages are about this long, split at paragraph breaks
LICENSE_NAMES = {
    "by-nc-sa/4.0": "CC BY-NC-SA 4.0",
    "by/4.0": "CC BY 4.0",
    "by-sa/4.0": "CC BY-SA 4.0",
    "by-nc/4.0": "CC BY-NC 4.0",
}

NS = {
    "c": "http://cnx.rice.edu/cnxml",
    "col": "http://cnx.rice.edu/collxml",
    "md": "http://cnx.rice.edu/mdml",
    "m": "http://www.w3.org/1998/Math/MathML",
}
C = "{http://cnx.rice.edu/cnxml}"


def book_url(slug):
    """The free online version (OpenStax redirects this to the book's first page)."""
    return f"https://openstax.org/books/{slug}"


def course_for_book(slug):
    for course_id, books in BOOKS.items():
        if any(s == slug for _, s in books):
            return course_id
    return None


# ---------- database ----------

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    slug         TEXT PRIMARY KEY,
    course_id    TEXT,
    title        TEXT NOT NULL,
    license      TEXT NOT NULL,
    license_url  TEXT NOT NULL,
    repo         TEXT,
    url          TEXT NOT NULL,
    imported_at  TEXT NOT NULL,
    counts_json  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sections (
    id          INTEGER PRIMARY KEY,
    book        TEXT NOT NULL REFERENCES books(slug) ON DELETE CASCADE,
    module      TEXT NOT NULL,
    number      TEXT,             -- "4.2", or NULL for a chapter introduction
    chapter     TEXT NOT NULL,
    title       TEXT NOT NULL,
    ord         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sections_book ON sections(book, ord);
CREATE TABLE IF NOT EXISTS passages (
    id          INTEGER PRIMARY KEY,
    book        TEXT NOT NULL REFERENCES books(slug) ON DELETE CASCADE,
    section_id  INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    heading     TEXT NOT NULL,
    text        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_passages_section ON passages(section_id);
CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY,
    book        TEXT NOT NULL REFERENCES books(slug) ON DELETE CASCADE,
    section_id  INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    stem        TEXT NOT NULL,
    options_json TEXT NOT NULL,
    answer      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_questions_section ON questions(section_id);
CREATE TABLE IF NOT EXISTS terms (
    id          INTEGER PRIMARY KEY,
    book        TEXT NOT NULL REFERENCES books(slug) ON DELETE CASCADE,
    section_id  INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    term        TEXT NOT NULL,
    meaning     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_terms_section ON terms(section_id);
"""
FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    heading, text, content='passages', content_rowid='id', tokenize='porter unicode61'
);
"""


def db_path():
    return Path(os.getenv("TEXTBOOK_DB_PATH") or DEFAULT_DB)


def connect(path=None):
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    try:
        conn.executescript(FTS)
    except sqlite3.OperationalError:  # SQLite built without FTS5: search falls back to LIKE
        pass
    return conn


def has_fts(conn):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'passages_fts'").fetchone() is not None


def exists():
    """Cheap check the app uses before opening the textbook database at all."""
    return db_path().exists()


# ---------- reading CNXML ----------

def _text(el, skip=("exercise", "glossary", "figure", "media", "table", "note", "footnote")):
    """Plain text of an element: MathML becomes plain symbols, figures/exercises are skipped."""
    if el is None:
        return ""
    parts = []

    def walk(node):
        tag = node.tag.split("}")[-1]
        if node is not el and tag in skip:
            if node.tail:
                parts.append(node.tail)
            return
        if tag == "math":
            parts.append(" " + _math_text(node) + " ")
        else:
            if node.text:
                parts.append(node.text)
            for child in node:
                walk(child)
        if node is not el and node.tail:
            parts.append(node.tail)

    walk(el)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _math_text(math):
    """MathML -> readable plain text, e.g. x^2 + 1, (a)/(b), sqrt(x)."""
    def conv(node):
        tag = node.tag.split("}")[-1]
        kids = list(node)
        if tag in ("mi", "mn", "mo", "mtext", "ms"):
            return (node.text or "").strip()
        if tag == "msup" and len(kids) == 2:
            return f"{conv(kids[0])}^{conv(kids[1])}"
        if tag == "msub" and len(kids) == 2:
            return f"{conv(kids[0])}_{conv(kids[1])}"
        if tag == "mfrac" and len(kids) == 2:
            return f"({conv(kids[0])})/({conv(kids[1])})"
        if tag == "msqrt":
            return "sqrt(" + "".join(conv(k) for k in kids) + ")"
        if tag == "mroot" and len(kids) == 2:
            return f"root({conv(kids[0])}, {conv(kids[1])})"
        return "".join(conv(k) for k in kids)
    return re.sub(r"\s+", " ", conv(math)).strip()


def _paragraph_blocks(content):
    """The readable blocks of a section, with the subsection heading each falls under."""
    blocks = []

    def walk(node, heading):
        tag = node.tag.split("}")[-1]
        if tag in ("exercise", "glossary", "figure", "media", "table", "footnote"):
            return
        if tag == "section":
            title = node.find(f"{C}title")
            heading = _text(title) if title is not None else heading
        if tag in ("para", "list", "equation", "note", "example"):
            text = _text(node)
            if len(text) > 30:
                blocks.append((heading, text))
            return
        for child in node:
            if child.tag == f"{C}title":
                continue
            walk(child, heading)

    walk(content, None)
    return blocks


def _passages(blocks, section_title, limit=PASSAGE_CHARS):
    """Group blocks into passages of about `limit` characters, never splitting a block."""
    out, current, heading = [], "", None
    for block_heading, text in blocks:
        head = block_heading or section_title
        if current and (len(current) + len(text) > limit or head != heading):
            out.append((heading, current))
            current = ""
        heading = head
        current = f"{current}\n\n{text}" if current else text
    if current:
        out.append((heading, current))
    return out


LETTER = re.compile(r"^\s*\(?([A-Ha-h])[).:]?\s*$")


def _questions(root):
    """Multiple-choice review questions with an official answer letter, 4 options only."""
    out = []
    for ex in root.iter(f"{C}exercise"):
        problem, solution = ex.find(f"{C}problem"), ex.find(f"{C}solution")
        if problem is None or solution is None:
            continue
        lst = None
        for candidate in problem.iter(f"{C}list"):
            if candidate.get("number-style") in ("lower-alpha", "upper-alpha"):
                lst = candidate
                break
        if lst is None:
            continue
        options = [_text(item, skip=()) for item in lst.findall(f"{C}item")]
        letter = LETTER.match(_text(solution, skip=()) or "")
        if len(options) != 4 or not letter or not all(options):
            continue
        if len({o.lower() for o in options}) != 4:
            continue
        # Options like "A, C, B" refer to labels in a figure or list we don't show.
        if any(re.fullmatch(r"[A-Ha-h](\s*[,;]\s*[A-Ha-h])+|[ivx]+", o.strip()) for o in options):
            continue
        # Questions that point at a figure or table can't be answered without it.
        if any(l.get("target-id", "").startswith(("fig", "tab", "Figure")) for l in problem.iter(f"{C}link")):
            continue
        stem = _text(problem, skip=("list",))
        if not stem or re.search(r"\b(figure|graph|diagram|table|image|shown|pictured)\b", stem, re.I):
            continue
        answer = "abcdefgh".index(letter.group(1).lower())
        if answer >= 4:
            continue
        out.append((stem, options, answer))
    return out


def _terms(root):
    out = []
    for d in root.iter(f"{C}definition"):
        term, meaning = d.find(f"{C}term"), d.find(f"{C}meaning")
        t, m = _text(term, skip=()), _text(meaning, skip=())
        if t and m and 3 <= len(m) <= 400:
            out.append((t, m))
    return out


def _walk_collection(content, chapter=None, state=None):
    """Yield (module_id, number, chapter_title) in book order."""
    state = state if state is not None else {"chapter": 0}
    modules = [n for n in content if n.tag == f"{{{NS['col']}}}module"]
    subs = [n for n in content if n.tag == f"{{{NS['col']}}}subcollection"]
    if chapter is not None and modules:
        state["chapter"] += 1
        ch = state["chapter"]
        section = 0
        for node in content:
            if node.tag == f"{{{NS['col']}}}module":
                if section == 0 and node is modules[0]:
                    yield node.get("document"), None, ch, chapter  # chapter introduction
                    section = 1
                    continue
                yield node.get("document"), f"{ch}.{section}", ch, chapter
                section += 1
            elif node.tag == f"{{{NS['col']}}}subcollection":
                title = node.find(f"{{{NS['md']}}}title")
                inner = node.find(f"{{{NS['col']}}}content")
                if inner is not None:
                    yield from _walk_collection(inner, _text(title) if title is not None else chapter, state)
        return
    for node in subs:
        title = node.find(f"{{{NS['md']}}}title")
        inner = node.find(f"{{{NS['col']}}}content")
        if inner is not None:
            yield from _walk_collection(inner, (title.text or "").strip() if title is not None else "", state)


def read_book(repo_dir, slug):
    """Parse one book from a downloaded osbooks repo. Returns a dict ready to store."""
    repo_dir = Path(repo_dir)
    books_xml = ET.parse(repo_dir / "META-INF" / "books.xml").getroot()
    entry = next((b for b in books_xml if b.get("slug") == slug), None)
    if entry is None:
        slugs = [b.get("slug") for b in books_xml]
        raise ValueError(f"book {slug!r} isn't in {repo_dir.name} (it has: {', '.join(slugs)})")
    collection = ET.parse((repo_dir / "META-INF" / entry.get("href")).resolve()).getroot()
    meta = collection.find(f"{{{NS['col']}}}metadata")
    if meta is None:
        meta = collection.find(f"{{{NS['md']}}}metadata")
    if meta is None:
        raise ValueError(f"{slug}: no metadata in its collection file")
    title = (meta.find(f"{{{NS['md']}}}title").text or slug).strip()
    lic = meta.find(f"{{{NS['md']}}}license")
    license_url = (lic.get("url") if lic is not None else "") or ""
    key = re.search(r"licenses/([a-z\-]+/\d\.\d)", license_url)
    license_name = LICENSE_NAMES.get(key.group(1) if key else "", (lic.text or "").strip() if lic is not None else "")
    if not license_name:
        raise ValueError(f"{slug}: no license found in its collection file")

    sections = []
    content = collection.find(f"{{{NS['col']}}}content")
    for ord_, (module, number, _ch, chapter) in enumerate(_walk_collection(content)):
        path = repo_dir / "modules" / module / "index.cnxml"
        if not path.exists():
            continue
        root = ET.parse(path).getroot()
        sec_title = _text(root.find(f"{C}title"), skip=()) or chapter
        body = root.find(f"{C}content")
        blocks = _paragraph_blocks(body) if body is not None else []
        sections.append({
            "module": module, "number": number, "chapter": chapter, "title": sec_title,
            "ord": ord_, "passages": _passages(blocks, sec_title),
            "questions": _questions(root), "terms": _terms(root),
        })
    return {"slug": slug, "title": title, "license": license_name, "license_url": license_url,
            "repo": repo_dir.name, "url": book_url(slug), "sections": sections}


def store_book(conn, book, course_id=None):
    """Replace a book in the database with freshly parsed content."""
    with conn:
        conn.execute("DELETE FROM books WHERE slug = ?", (book["slug"],))
        if has_fts(conn):
            conn.execute("INSERT INTO passages_fts(passages_fts) VALUES ('rebuild')")
        counts = {"sections": 0, "passages": 0, "questions": 0, "terms": 0}
        conn.execute(
            "INSERT INTO books (slug, course_id, title, license, license_url, repo, url, imported_at, counts_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}')",
            (book["slug"], course_id or course_for_book(book["slug"]), book["title"], book["license"],
             book["license_url"], book["repo"], book["url"], datetime.now().isoformat(timespec="seconds")))
        for s in book["sections"]:
            sid = conn.execute(
                "INSERT INTO sections (book, module, number, chapter, title, ord) VALUES (?, ?, ?, ?, ?, ?)",
                (book["slug"], s["module"], s["number"], s["chapter"], s["title"], s["ord"])).lastrowid
            counts["sections"] += 1
            for heading, text in s["passages"]:
                pid = conn.execute("INSERT INTO passages (book, section_id, heading, text) VALUES (?, ?, ?, ?)",
                                   (book["slug"], sid, heading, text)).lastrowid
                if has_fts(conn):
                    conn.execute("INSERT INTO passages_fts(rowid, heading, text) VALUES (?, ?, ?)",
                                 (pid, heading, text))
                counts["passages"] += 1
            for stem, options, answer in s["questions"]:
                conn.execute("INSERT INTO questions (book, section_id, stem, options_json, answer) VALUES (?, ?, ?, ?, ?)",
                             (book["slug"], sid, stem, json.dumps(options), answer))
                counts["questions"] += 1
            for term, meaning in s["terms"]:
                conn.execute("INSERT INTO terms (book, section_id, term, meaning) VALUES (?, ?, ?, ?)",
                             (book["slug"], sid, term, meaning))
                counts["terms"] += 1
        conn.execute("UPDATE books SET counts_json = ? WHERE slug = ?", (json.dumps(counts), book["slug"]))
    return counts


def remove_book(conn, slug):
    with conn:
        conn.execute("DELETE FROM books WHERE slug = ?", (slug,))
        if has_fts(conn):
            conn.execute("INSERT INTO passages_fts(passages_fts) VALUES ('rebuild')")


# ---------- downloading and importing ----------

class ImportFailed(Exception):
    """A book couldn't be downloaded or read. The message is meant for the student."""


def download(repo, log=print):
    """Clone a repo's text only (no media) into user_data/openstax/<repo>. Returns its path.
    A repo that's already downloaded is reused, so re-importing works offline."""
    dest = SOURCE_DIR / repo
    if (dest / "META-INF" / "books.xml").exists():
        log(f"  {repo}: already downloaded")
        return dest
    if not shutil.which("git"):
        raise ImportFailed("git isn't installed (on a Mac: run xcode-select --install).")
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    url = REPO_URL.format(repo=repo)
    log(f"  downloading {url} (text only)...")
    start = time.time()

    def run(*args):
        subprocess.run(args, check=True, capture_output=True, text=True, timeout=600)

    try:
        run("git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", url, str(dest))
        run("git", "-C", str(dest), "sparse-checkout", "set", "--no-cone",
            "/META-INF/", "/collections/", "/modules/", "/LICENSE")
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(dest, ignore_errors=True)
        detail = (exc.stderr or "").strip().splitlines()
        raise ImportFailed("Download failed. Check the internet connection and try again."
                           + (f" ({detail[-1]})" if detail else "")) from exc
    except (subprocess.TimeoutExpired, OSError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise ImportFailed(f"Download failed: {exc}") from exc
    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file() and ".git" not in f.parts)
    log(f"  downloaded {size / 1e6:.1f} MB in {time.time() - start:.0f}s")
    return dest


def import_book(conn, course_id, repo, slug, source=None, log=print):
    """Download (unless `source` is given), parse and store one book. Returns its counts."""
    repo_dir = Path(source).expanduser() if source else download(repo, log)
    log(f"  reading {slug}...")
    start = time.time()
    try:
        book = read_book(repo_dir, slug)
    except (ValueError, OSError, ET.ParseError) as exc:
        raise ImportFailed(f"Couldn't read {slug}: {exc}") from exc
    counts = store_book(conn, book, course_id)
    log(f"  {book['title']} ({book['license']}): {counts['sections']} sections, "
        f"{counts['passages']} passages, {counts['questions']} review questions, "
        f"{counts['terms']} glossary terms [{time.time() - start:.1f}s]")
    return counts


def import_course(course_id, log=print):
    """Import every book for a catalog course into the textbook database."""
    if course_id not in BOOKS:
        raise ImportFailed(f"No OpenStax book is listed for {course_id!r}.")
    conn = connect()
    try:
        return {slug: import_book(conn, course_id, repo, slug, log=log)
                for repo, slug in BOOKS[course_id]}
    finally:
        conn.close()


# ---------- using books ----------

def list_books(conn):
    rows = [dict(r) for r in conn.execute("SELECT * FROM books ORDER BY title")]
    for r in rows:
        r["counts"] = json.loads(r.pop("counts_json"))
    return rows


def books_for_course(conn, course_id):
    return [b for b in list_books(conn) if b["course_id"] == course_id]


def attribution(book):
    """The credit line the license asks for: OpenStax, the title, a link, the license."""
    return f"{book['title']} by OpenStax ({book['license']}), free at {book['url']}"


def section_label(row):
    return f"{row['number']} {row['title']}" if row["number"] else f"{row['chapter']}: Introduction"


STOP = set("the a an and or of to in on for with is are what how why does do about this that".split())


def _fts_query(text):
    words = [w for w in re.findall(r"[A-Za-z0-9]+", str(text).lower()) if w not in STOP and len(w) > 1]
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words))[:500]


def _key_words(text):
    return [w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if w not in STOP and len(w) > 2]


def relevant(hit, query):
    """True if at least half of the query's key words appear in the passage (by their first
    5 letters, so "organelles" matches "organelle"). Keeps unrelated books out: "underwater
    basket weaving" shouldn't pull in ecology because of the word "water"."""
    words = _key_words(query)
    if not words:
        return False
    text = f"{hit['heading']} {hit['title']} {hit['text']}".lower()
    found = sum(1 for w in words if w[:5] in text)
    return found * 2 >= len(words)


def search(conn, books, query, k=3, strict=True):
    """The k passages that best match the query, across the given book slugs.
    strict: only passages that pass relevant() (an unrelated query returns nothing)."""
    if not books or not str(query).strip():
        return []
    marks = ",".join("?" * len(books))
    q = _fts_query(query)
    if not q:
        return []
    if has_fts(conn):
        rows = conn.execute(
            f"""SELECT p.id, p.heading, p.text, s.id AS section_id, s.number, s.title, s.chapter,
                       b.slug, b.title AS book_title, b.license, b.url
                FROM passages_fts f
                JOIN passages p ON p.id = f.rowid
                JOIN sections s ON s.id = p.section_id
                JOIN books b ON b.slug = p.book
                WHERE passages_fts MATCH ? AND p.book IN ({marks})
                ORDER BY bm25(passages_fts, 4.0, 1.0) LIMIT ?""",
            (q, *books, k)).fetchall()
    else:  # no FTS5: slower, simpler match on the first word
        word = q.split(" OR ")[0].strip('"')
        rows = conn.execute(
            f"""SELECT p.id, p.heading, p.text, s.id AS section_id, s.number, s.title, s.chapter,
                       b.slug, b.title AS book_title, b.license, b.url
                FROM passages p JOIN sections s ON s.id = p.section_id JOIN books b ON b.slug = p.book
                WHERE p.book IN ({marks}) AND (p.heading LIKE ? OR p.text LIKE ?) LIMIT ?""",
            (*books, f"%{word}%", f"%{word}%", k)).fetchall()
    hits = [dict(r) | {"label": section_label(r)} for r in rows]
    if strict and hits and not relevant(hits[0], query):
        return []  # the best match isn't about this topic: the book doesn't cover it
    return hits


def passages_for_prompt(conn, books, query, budget, k=3, topic=None):
    """(prompt text, sources) for the best passages, staying within `budget` characters.

    topic: passages from the chapter(s) that teach the topic go first, so "why do plants
    need light?" while studying Photosynthesis stays in the photosynthesis chapter.
    """
    hits = search(conn, books, query, k * 3 if topic else k)
    if topic and hits:
        home = set(best_chapters(conn, books, topic)[:2])
        hits.sort(key=lambda h: (h["slug"], h["chapter"]) not in home)  # stable: keeps rank
    parts, sources, used = [], [], 0
    for h in hits[:k]:
        head = f"--- {h['book_title']} (OpenStax), section {h['label']} ---\n"
        room = budget - used - len(head)
        if room < 200:
            break
        text = h["text"][:room]
        parts.append(head + text)
        used += len(head) + len(text)
        source = {"book": h["book_title"], "section": h["label"], "license": h["license"],
                  "url": h["url"], "slug": h["slug"]}
        if source not in sources:
            sources.append(source)
    return "\n\n".join(parts), sources


def _source(row):
    return {"source": f"OpenStax {row['book_title']}, section {section_label(row)}",
            "source_url": row["url"], "source_license": row["license"]}


def best_chapters(conn, books, topic, k=10):
    """(book, chapter) pairs that best match the topic, best first.

    Review questions sit at particular spots in a chapter, so a quiz draws on the whole
    chapter that matches, not just the matching paragraphs (which can be scattered
    across chapters that merely mention a word). In order of strength:
      1. a chapter whose title contains the topic ("Evolution and the Origin of Species")
      2. the chapter whose glossary defines the topic ("mitosis" is defined in 10.2)
      3. the chapters with the best-matching passages
    """
    if not books:
        return []
    hits = search(conn, books, topic, k)
    if not hits:
        return []  # the book doesn't cover this topic
    vote = {}
    for rank, h in enumerate(hits):
        key = (h["slug"], h["chapter"])
        vote[key] = vote.get(key, 0) + 1 / (rank + 1)
    phrase = " ".join(_key_words(topic))
    marks = ",".join("?" * len(books))
    strong = []
    if phrase:
        titled = conn.execute(
            f"SELECT DISTINCT book, chapter FROM sections WHERE book IN ({marks}) AND lower(chapter) LIKE ?",
            (*books, f"%{phrase}%")).fetchall()
        strong += [tuple(r) for r in titled]
        forms = {phrase, phrase + "s", phrase.removesuffix("s"), phrase.removesuffix("es")}
        defined = conn.execute(
            f"""SELECT DISTINCT t.book, s.chapter FROM terms t JOIN sections s ON s.id = t.section_id
                WHERE t.book IN ({marks}) AND lower(t.term) IN ({",".join("?" * len(forms))})""",
            (*books, *forms)).fetchall()
        strong += [tuple(r) for r in defined if tuple(r) not in strong]
    strong.sort(key=lambda key: -vote.get(key, 0))  # among strong matches, best passages first
    rest = sorted((key for key in vote if key not in strong), key=lambda key: -vote[key])
    return list(dict.fromkeys(strong + rest))


def quiz_questions(conn, books, topic, n, seed=None):
    """Up to n questions for a topic, right by construction: the book's review questions
    (official keys) first, then glossary questions ("Which term means ...?"), drawn from
    the chapter(s) that best match the topic."""
    rng = random.Random(seed)
    cols = "s.number, s.title, s.chapter, b.title AS book_title, b.license, b.url"
    review, glossary = [], []
    for slug, chapter in best_chapters(conn, books, topic)[:2]:
        where = "FROM {t} x JOIN sections s ON s.id = x.section_id JOIN books b ON b.slug = x.book " \
                "WHERE x.book = ? AND s.chapter = ?"
        rows = [dict(r) for r in conn.execute(
            f"SELECT x.stem, x.options_json, x.answer, {cols} " + where.format(t="questions"), (slug, chapter))]
        rng.shuffle(rows)
        for r in rows:
            review.append({"question": r["stem"], "options": json.loads(r["options_json"]),
                           "answer": r["answer"],
                           "explanation": "This is the answer key from the book's own review questions.",
                           "verified": True, "corrected": False, "model_said": None,
                           "checked_by": "textbook", **_source(r)})
        terms = [dict(r) for r in conn.execute(
            f"SELECT x.term, x.meaning, {cols} " + where.format(t="terms"), (slug, chapter))]
        pool = sorted({t["term"] for t in terms})
        rng.shuffle(terms)
        for t in terms:
            others = [o for o in pool if o.lower() != t["term"].lower()
                      and o.lower() not in t["term"].lower() and t["term"].lower() not in o.lower()]
            if len(others) < 3 or t["term"].lower() in t["meaning"].lower():
                continue
            options = rng.sample(others, 3) + [t["term"]]
            rng.shuffle(options)
            glossary.append({"question": f"Which term means: “{t['meaning']}”?", "options": options,
                             "answer": options.index(t["term"]),
                             "explanation": f"From the glossary of OpenStax {t['book_title']}: "
                                            f"{t['term']} - {t['meaning']}.",
                             "verified": True, "corrected": False, "model_said": None,
                             "checked_by": "textbook", **_source(t)})
        if len(review) + len(glossary) >= n:
            break
    # Mostly review questions, with a glossary question or two for variety.
    n_glossary = min(len(glossary), max(1, n // 4), max(0, n - len(review))) if glossary else 0
    n_glossary = max(n_glossary, n - len(review))
    return (review[: n - min(n_glossary, len(glossary))] + glossary[:n_glossary])[:n]
