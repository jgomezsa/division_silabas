"""Find Spanish words by syllable.

Lists the words whose first syllable is the given one. If there are fewer
than 20, it also lists words that contain that syllable in any other position.
Only base forms are listed (verbs in infinitive, nouns and adjectives in
masculine singular) unless --all-forms is given. Results are sorted by
frequency of use (most common first).

Usage:
    python find_words.py pa
    python find_words.py tra --limit 0        # no limit
    python find_words.py ció --exact          # accents must match
    python find_words.py pa --all-forms       # also conjugations and plurals
"""
import argparse
import sqlite3
import sys
from pathlib import Path

from build_db import DB_PATH, strip_accents

MIN_STARTING = 20


def search(con, syllable, first_only, exact, all_forms=False):
    """Words with ``syllable`` first (or elsewhere), most frequent first.

    By default only lemmas (infinitives, singular...), ranked by the frequency
    of all their forms; with ``all_forms`` also conjugations, plurals...
    """
    plain = strip_accents(syllable)
    freq_col = "w.freq" if all_forms else "w.lemma_freq"
    sql = (
        f"SELECT w.word, w.hyphenated, {freq_col} FROM syllables s "
        "JOIN words w ON w.id = s.word_id "
        "WHERE s.syllable_plain = ? AND " + ("s.pos = 0" if first_only else "s.pos > 0")
    )
    if not all_forms:
        sql += " AND w.is_lemma = 1"
    params = [plain]
    if exact:
        sql += " AND s.syllable = ?"
        params.append(syllable)
    if not first_only:
        # words that start with the syllable are already in the first list
        sql += (
            " AND NOT EXISTS (SELECT 1 FROM syllables f WHERE f.word_id = s.word_id"
            " AND f.syllable_plain = ? AND f.pos = 0" + (" AND f.syllable = ?" if exact else "") + ")"
        )
        params += params[:]
    sql += f" GROUP BY w.id ORDER BY {freq_col} DESC, w.word"
    return con.execute(sql, params).fetchall()


def print_rows(rows):
    for word, hyphenated, freq in rows:
        print(f"  {word:<25} {hyphenated:<30} {freq:>10,}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("syllable", help="Spanish syllable, e.g. 'pa', 'tra', 'ción'")
    parser.add_argument("--limit", type=int, default=50,
                        help="max words per list (0 = all, default 50)")
    parser.add_argument("--exact", action="store_true",
                        help="match accents exactly (by default 'cion' also finds 'ción')")
    parser.add_argument("--plain", action="store_true",
                        help="print only the words, one per line")
    parser.add_argument("--all-forms", action="store_true",
                        help="include conjugations, plurals and feminines (default: "
                             "only infinitives and masculine singular)")
    args = parser.parse_args(argv)

    if not Path(DB_PATH).exists():
        sys.exit(f"Database not found at {DB_PATH}. Run: python build_db.py")

    syllable = args.syllable.strip().lower()
    con = sqlite3.connect(DB_PATH)

    starting = search(con, syllable, True, args.exact, args.all_forms)
    containing = []
    if len(starting) < MIN_STARTING:
        containing = search(con, syllable, False, args.exact, args.all_forms)

    if args.plain:
        for word, _, _ in (starting[: args.limit or None] + containing[: args.limit or None]):
            print(word)
        return

    shown = starting[: args.limit or None]
    print(f"Words starting with the syllable '{syllable}': {len(starting):,}"
          + (f" (showing {len(shown)})" if len(shown) < len(starting) else ""))
    print_rows(shown)
    if len(starting) < MIN_STARTING:
        shown = containing[: args.limit or None]
        print(f"\nFewer than {MIN_STARTING}; words containing '{syllable}': {len(containing):,}"
              + (f" (showing {len(shown)})" if len(shown) < len(containing) else ""))
        print_rows(shown)


if __name__ == "__main__":
    main()
