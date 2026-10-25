"""Check quiz questions against the student's own notes (their Materials for the topic).

When a topic has notes, the model is asked to give, for each question, the sentence from
the notes that the answer comes from ("source"). A question passes only if:
  1. that sentence really is in the notes (allowing small differences in spacing,
     punctuation and quote marks), and
  2. it supports the keyed option better than every other option: most of the option's
     key words appear in the sentence, and no other option matches it as well.
If the sentence clearly supports a different option, the key is corrected to that one.
Otherwise the question is left unchecked.

This is a word-overlap check, not understanding, so it's labeled "checked against your
notes", which is weaker than a calculation.
"""
import difflib
import re
import unicodedata

from mathcheck import MathError, _claimed_index

STOPWORDS = set("""
a an the and or but of to in on at by for with from as is are was were be been being it its
this that these those which who whom what when where why how than then so such not no do does
did has have had can could will would should may might must shall into onto over under about
also very more most less least each every any all some many much one two three their there they
them his her he she you your we our us i me my
""".split())
MIN_SUPPORT = 0.6  # share of an option's key words that must appear in the source sentence


def _norm(text):
    text = unicodedata.normalize("NFKC", str(text)).lower()
    text = text.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-",
                                         "—": "-"}))
    text = re.sub(r"[*_`#>|]+", " ", text)  # Markdown
    return re.sub(r"\s+", " ", text).strip()


def _stem(word):
    for suffix in ("ing", "ies", "es", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def key_words(text):
    words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", _norm(text))
    return {_stem(w) for w in words if w not in STOPWORDS and (len(w) > 2 or w.isdigit())}


def find_in_notes(source, notes):
    """True if the source sentence appears in the notes (allowing small differences)."""
    # Compare letters, digits and spaces only, so "cell's DNA," matches "cells DNA".
    bare = lambda t: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", "", _norm(t))).strip()
    src, text = bare(source), bare(notes)
    if len(src) < 15:
        return False
    if src in text:
        return True
    # Tolerate small differences: the longest common run must cover 90% of the quote.
    matcher = difflib.SequenceMatcher(None, text, src, autojunk=False)
    match = matcher.find_longest_match(0, len(text), 0, len(src))
    if match.size >= 0.9 * len(src):
        return True
    window = text[max(0, match.a - match.b): match.a - match.b + len(src) + 20]
    return difflib.SequenceMatcher(None, window, src, autojunk=False).ratio() >= 0.9


def support(option, source):
    words = key_words(option)
    if not words:
        return 0.0
    return len(words & key_words(source)) / len(words)


def check_grounded(q, notes):
    """Verify a plain-text question against the notes. Returns a question dict (same
    shape as the other checkers, plus "source"), or raises MathError (leave it unchecked)."""
    source = str(q.get("source") or "").strip().strip('"“”')
    if not source:
        raise MathError("no source sentence given")
    if len(source) > 500:
        raise MathError("source is too long")
    if not find_in_notes(source, notes):
        raise MathError("source sentence isn't in the notes")
    options = [str(o).strip() for o in q.get("options") or []]
    if len(options) != 4 or len({_norm(o) for o in options}) != 4:
        raise MathError("need 4 different options")
    scores = [support(o, source) for o in options]
    best = max(scores)
    winners = [i for i, s in enumerate(scores) if s == best]
    if best < MIN_SUPPORT or len(winners) != 1:
        raise MathError("the source doesn't clearly support one option")
    answer = winners[0]
    claimed = _claimed_index(q.get("answer"))
    corrected = answer != claimed
    explanation = str(q.get("explanation") or "").strip()
    if corrected or not explanation:
        explanation = f"From your notes: “{source}”"
    return {
        "question": str(q.get("question") or "").strip(),
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "verified": True,
        "corrected": corrected,
        "model_said": options[claimed] if (corrected and claimed is not None) else None,
        "checked_by": "notes",
        "source": source,
    }
