"""Download free OpenStax textbooks and import them into Clutch (user_data/textbooks.db).

Only the text is downloaded (no images), so a book is a few MB instead of hundreds.
Needs git and an internet connection the first time; after that everything is offline.

You can also import from the app: a course with a book offers it on the Progress page.

Usage (from backend/, with the venv active):
    python import_openstax.py --list               # books available for each course
    python import_openstax.py biology              # download + import the book(s) for a course
    python import_openstax.py biology-2e           # ...or one book by its slug
    python import_openstax.py --all                # every book in the list (~200 MB of text)
    python import_openstax.py biology --from ~/Downloads/osbooks-biology-bundle   # already downloaded
    python import_openstax.py --remove biology-2e  # delete a book from Clutch

Clutch picks new books up right away (no restart). Textbooks stay out of git (user_data/ is ignored).

OpenStax books are licensed CC BY-NC-SA 4.0 (some CC BY 4.0): free for non-commercial use
with credit to OpenStax. Clutch shows the title, license and a link wherever it uses one.
"""
import argparse
import sys

import textbooks


def targets(name):
    """A course id or a book slug -> [(course_id, repo, slug)]."""
    if name in textbooks.BOOKS:
        return [(name, repo, slug) for repo, slug in textbooks.BOOKS[name]]
    for course_id, books in textbooks.BOOKS.items():
        for repo, slug in books:
            if slug == name:
                return [(course_id, repo, slug)]
    sys.exit(f"Unknown course or book {name!r}. Run with --list to see them.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", nargs="?", help="a course id (e.g. biology) or book slug (e.g. biology-2e)")
    parser.add_argument("--list", action="store_true", help="show the books for each course")
    parser.add_argument("--all", action="store_true", help="import every book")
    parser.add_argument("--from", dest="source", help="import from a repo you already downloaded")
    parser.add_argument("--remove", metavar="SLUG", help="delete an imported book")
    args = parser.parse_args()

    conn = textbooks.connect()
    if not textbooks.has_fts(conn):
        print("Note: this SQLite has no full-text search (FTS5), so textbook search will be slower.")
    imported = {b["slug"]: b for b in textbooks.list_books(conn)}

    if args.list or not (args.name or args.all or args.remove):
        print("Free OpenStax textbooks for Clutch courses:\n")
        for course_id, books in textbooks.BOOKS.items():
            for repo, slug in books:
                mark = "imported" if slug in imported else ""
                print(f"  {course_id:18} {slug:34} {mark}")
        print(f"\nTextbook database: {textbooks.db_path()}")
        print("Import one with: python import_openstax.py <course or book>")
        return
    if args.remove:
        if args.remove not in imported:
            sys.exit(f"{args.remove} isn't imported.")
        textbooks.remove_book(conn, args.remove)
        print(f"Removed {args.remove}.")
        return
    todo = [t for name in textbooks.BOOKS for t in targets(name)] if args.all else targets(args.name)
    if args.source and len(todo) != 1 and len({repo for _, repo, _ in todo}) != 1:
        sys.exit("--from works with one book (or one course whose books share a repo).")
    for course_id, repo, slug in todo:
        print(f"{slug}:")
        try:
            textbooks.import_book(conn, course_id, repo, slug, args.source)
        except textbooks.ImportFailed as exc:
            sys.exit(str(exc))
    size = textbooks.db_path().stat().st_size / 1e6
    print(f"\nDone. Textbook database is {size:.1f} MB. Clutch will use it right away.")


if __name__ == "__main__":
    main()
