"""Download the word sources, syllabify every word and build data/silabas.db.

Sources:
  * LibreOffice Spanish dictionary for Spain (RLA-ES, es_ES variant, so no
    Latin American regionalisms), expanded with its affix rules: conjugations,
    plurals, enclitics...
  * Lemario general del español and verb conjugation list (olea/lemarios,
    public domain): more lemmas, and telling lemmas (base forms) apart from
    inflected forms such as "fue" or "soy".
  * OpenSubtitles 2018 frequency list (hermitdave/FrequencyWords): gives each
    word a frequency and adds colloquial forms that the dictionary does not
    list but can be derived from a dictionary word (pásame, nuevecita...).

Every word is stored with ``is_lemma``: 1 for base forms (infinitives,
masculine singular, invariable words), 0 for conjugations, plurals, feminines...
"""
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

from hunspell_expand import expand_entries
from syllabify import syllabify

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "silabas.db"

LO_URL = "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/es/"
# Other variants (AR, MX, CO...) add each country's regionalisms; only Spain is used.
REGIONS = ["ES"]
FREQ_URL = (
    "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/"
    "content/2018/es/es_full.txt"
)
FREQ_FILE = RAW / "freq_es_full.txt"
LEMARIOS_URL = "https://raw.githubusercontent.com/olea/lemarios/master/"
LEMARIO_FILE = RAW / "lemarios" / "lemario-general-del-espanol.txt"
CONJUGATIONS_FILE = RAW / "lemarios" / "verbos-espanol-conjugaciones.txt"
INFINITIVES_FILE = RAW / "lemarios" / "verbos-espanol.txt"
# The database is a derived work of the data sources (see DATA_LICENSE.md)
DB_METADATA = {
    "license": "GPL-3.0",
    "attribution": (
        "Derived from: Spanish Hunspell dictionary es_ES by the RLA-ES project "
        "(GPL-3.0-or-later / LGPL-3.0-or-later / MPL-1.1-or-later), "
        "https://github.com/LibreOffice/dictionaries/tree/master/es; "
        "FrequencyWords Spanish 2018 list by Hermit Dave (CC BY-SA 4.0), based on "
        "the OpenSubtitles2018 corpus (OPUS, www.opensubtitles.org), "
        "https://github.com/hermitdave/FrequencyWords; "
        "Lemarios by Ismael Olea and contributors (public domain), "
        "https://github.com/olea/lemarios. "
        "Modified: words were syllabified, filtered and combined."
    ),
    "details": "https://github.com/jgomezsa/division_silabas/blob/main/DATA_LICENSE.md",
}
MIN_FREQ_EXTRA = 5  # minimum occurrences for a word that is only in the frequency list
MIN_STEM = 3  # shorter stems are too ambiguous for derivations (alice, erica, stone...)

SPANISH_WORD = re.compile(r"^[a-záéíóúüñ]+$")
ACCENTED = re.compile(r"[áéíóú]")
ENCLITIC = re.compile(r"(?:me|te|se|nos|os|le|les|lo|la|los|las)(?:lo|la|los|las|le|les)?$")
# Diminutive/augmentative/superlative suffix + ending, on the accent-less word.
# An empty ending is only valid for the accented -ón (cajón).
DIMINUTIVE = re.compile(
    r"(?:(?:ecit|cit|it|ecill|cill|ill|uch|az|isim)(o|a|os|as)"
    r"|ot(o|a|e|os|as|es)|on(a|es|as|))$"
)
PREFIX = re.compile(
    r"^(?:re|des|in(?![bp])|im(?=[bp])|pre|super|súper|anti|ex|auto|mini|multi|contra|sobre|semi|"
    r"neo|ultra|micro|macro|mega|hiper|archi|requete|post|pos|sub|co|bi|tri|inter)"
)


def strip_accents(text):
    """á->a, é->e... but keep ñ and ü (güe and gue are different syllables)."""
    out = []
    for ch in text:
        if ch in "ñÑüÜ":
            out.append(ch)
        else:
            out.append(
                "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c))
            )
    return "".join(out)


def download(url, dest):
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    urllib.request.urlretrieve(url, dest)


def download_sources():
    for region in REGIONS:
        for ext in ("aff", "dic"):
            name = f"es_{region}.{ext}"
            download(LO_URL + name, RAW / "hunspell" / name)
    download(LO_URL + "README_hunspell_es.txt", RAW / "hunspell" / "README_hunspell_es.txt")
    download(FREQ_URL, FREQ_FILE)
    for path in (LEMARIO_FILE, CONJUGATIONS_FILE, INFINITIVES_FILE):
        download(LEMARIOS_URL + path.name, path)
    download(LEMARIOS_URL + "COPYRIGHT", RAW / "lemarios" / "COPYRIGHT")


def load_dictionary():
    """Return (stem -> set of forms, lowercased proper nouns) from the dictionary."""
    entries, proper = {}, set()
    for region in REGIONS:
        base = RAW / "hunspell" / f"es_{region}"
        for stem, forms in expand_entries(base.with_suffix(".aff"), base.with_suffix(".dic")):
            # skip proper nouns, acronyms and multi-word / punctuated entries
            if SPANISH_WORD.match(stem):
                entries.setdefault(stem, set()).update(f for f in forms if SPANISH_WORD.match(f))
            elif stem[:1].isupper():
                proper.update(f.lower() for f in forms)
    return entries, proper


def load_word_list(path):
    with open(path, encoding="utf-8") as f:
        return {w for w in (line.strip() for line in f) if SPANISH_WORD.match(w)}


def is_gender_or_number(stem, form):
    """True if ``form`` is a plural or feminine of ``stem`` (gatas, profesora)."""
    stem, form = strip_accents(stem), strip_accents(form)
    if form == stem:
        return False
    singulars = {form}
    if form.endswith("s"):
        singulars.add(form[:-1])
    if form.endswith("es"):
        singulars.add(form[:-2])
    for base in singulars:
        if base == stem:
            return True  # plural: gatos, camiones
        if base.endswith("a") and stem in (base[:-1] + "o", base[:-1]):
            return True  # feminine: gata, profesora
    return False


def find_lemmas(entries, lemario, conjugations, infinitives):
    """Base forms among the dictionary stems and the lemario."""
    verbs = infinitives | {s for s in entries if s.endswith(("ar", "er", "ir", "ír"))}
    # Forms generated from another non-verb entry: gata (gato), fría (frío),
    # profesores (profesor). Verbs are left out so casa (casar) stays a lemma.
    inflected = set()
    for stem, forms in entries.items():
        if stem not in verbs:
            inflected.update(f for f in forms if is_gender_or_number(stem, f))
    verb_forms = conjugations - infinitives

    lemmas = set()
    for w in set(entries) | lemario:
        if w in inflected:
            continue
        if w in lemario or w not in verb_forms:  # fue, soy... (but era, vino, traje)
            lemmas.add(w)
    return lemmas


def load_frequencies():
    freq = {}
    with open(FREQ_FILE, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2 and SPANISH_WORD.match(parts[0]):
                freq[parts[0]] = int(parts[1])
    return freq


# The dictionary lists the forms of the most irregular verbs as separate
# entries (fue, estoy, puedo); these patterns give them back to their verb so
# the infinitive is ranked by all its forms. Order matters (decir before dar).
IRREGULAR_VERBS = [
    ("ser", r"soy|eres|es|somos|sois|son|se[aá]\w*|er[ae]\w*|éra\w*|sido|siendo|ser[éáí]\w*|fu\w*"),
    ("ir", r"voy|vas|va|vamos|vais|van|ve|vay\w*|ib\w*|íb\w*|ir[éáí]\w*|ido|yendo"),
    ("estar", r"est[aáeéu]\w*"),
    ("haber", r"ha|has|he|hemos|han|hay\w*|hab\w*|hub\w*"),
    ("poder", r"pued\w*|pud\w*|pod\w*"),
    ("decir", r"di[rj]\w*|dic\w*"),
    ("dar", r"doy|d[aáeéií]\w*"),
    ("jugar", r"jue?g\w*"),
    ("andar", r"and\w*"),
    ("oler", r"huel\w*"),
    ("soler", r"sol\w*"),
    ("caber", r"quep\w*"),
]
IRREGULAR_RE = [(verb, re.compile(f"(?:{pattern})$")) for verb, pattern in IRREGULAR_VERBS]


def irregular_verb(form):
    return next((verb for verb, rx in IRREGULAR_RE if rx.match(form)), None)


def lemma_frequencies(entries, lemmas, freq):
    """Frequency of each dictionary stem counting all its forms (ser: es, fue...).

    A form that is a lemma itself only counts for itself (para, not parar). A
    form shared with nouns/adjectives goes to them (una: uno, not unir); one
    shared only among verbs is split between them.
    """
    owners = {}
    for stem, forms in entries.items():
        for f in forms - lemmas:
            owners.setdefault(f, []).append(stem)
    is_verb = lambda s: s.endswith(("ar", "er", "ir", "ír"))
    total = {stem: freq.get(stem, 0) for stem in entries}
    for f, stems in owners.items():
        n = freq.get(f, 0)
        if not n:
            continue
        if stems == [f] and irregular_verb(f) in total:  # standalone form: fue, estoy
            stems = [irregular_verb(f)]
        stems = [s for s in stems if not is_verb(s)] or stems
        for s in stems:
            total[s] += n / len(stems)
    return {stem: round(n) for stem, n in total.items()}


def classify_derived(word, known_plain, lemma_plain):
    """Classify a word missing from the dictionary by how it derives from one.

    Returns "lemma" (gatito, casita, grandote, superpeligroso), "form"
    (gatitos, pásame) or None when it is not a regular derivation.
    """
    plain = strip_accents(word)
    m = ENCLITIC.search(plain)
    if m and m.start() >= MIN_STEM + 1:
        stem = plain[: m.start()]
        # Enclitics attach to infinitives (-r), gerunds (-ndo) and imperatives;
        # imperatives of 2+ syllables then carry a written accent (pásame).
        verb_like = stem.endswith(("r", "ndo", "d")) or ACCENTED.search(word)
        if verb_like and (stem in known_plain or stem + "s" in known_plain):  # arreglémo(s)nos
            return "form"
    m = PREFIX.match(plain)
    if m and len(plain) - m.end() >= 5 and plain[m.end():] in known_plain:
        return "lemma" if plain[m.end():] in lemma_plain else "form"
    m = DIMINUTIVE.search(plain)
    if m and m.start() >= MIN_STEM:
        ending = next(g for g in m.groups() if g is not None)
        if ending == "" and not word.endswith("ón"):
            return None
        stem = plain[: m.start()]
        stems = [stem]
        # c/qu, g/gu, z/c spelling changes: poquito, amiguito, pedacito
        for a, b in (("qu", "c"), ("gu", "g"), ("c", "z")):
            if stem.endswith(a):
                stems.append(stem[: -len(a)] + b)
        if any(st + end in known_plain for st in stems for end in ("", "o", "a", "e")):
            # Base form: masculine singular (gatito, grandote, cajón), or the
            # base noun's own gender (casita from casa).
            if ending in ("o", "e", "") or any(st + ending in lemma_plain for st in stems):
                return "lemma"
            return "form"
    return None


def select_extra_words(freq, known_words, lemmas, proper_nouns):
    """Frequency-list words missing from the dictionary but derived from it.

    Returns {word: is_lemma}.
    """
    known_plain = {strip_accents(w) for w in known_words}
    lemma_plain = {strip_accents(w) for w in lemmas}
    # Most frequent spelling for each accent-less form, to discard misspellings
    # such as "mirandote" when "mirándote" is more common.
    best = {}
    for w, c in freq.items():
        p = strip_accents(w)
        if c > freq.get(best.get(p), -1):
            best[p] = w
    extra = {}
    for w, c in freq.items():
        if c < MIN_FREQ_EXTRA or w in known_words or w in proper_nouns:
            continue
        p = strip_accents(w)
        if p in known_plain or best[p] != w:  # misspelling of a known word
            continue
        kind = classify_derived(w, known_plain, lemma_plain)
        if kind:
            extra[w] = kind == "lemma"
    return extra


def build():
    t0 = time.time()
    print("Downloading sources (only missing files)...")
    download_sources()

    print("Expanding Hunspell dictionary...")
    entries, proper_nouns = load_dictionary()
    dict_words = set().union(*entries.values())
    print(f"  {len(dict_words):,} dictionary word forms from {len(entries):,} entries")

    print("Finding lemmas...")
    lemario = load_word_list(LEMARIO_FILE)
    lemmas = find_lemmas(
        entries, lemario, load_word_list(CONJUGATIONS_FILE), load_word_list(INFINITIVES_FILE)
    )
    print(f"  {len(lemmas):,} lemmas ({len(lemario - dict_words):,} only in the lemario)")

    print("Loading frequency list...")
    freq = load_frequencies()
    known_words = dict_words | lemario
    extra = select_extra_words(freq, known_words, lemmas, proper_nouns)
    print(f"  {len(extra):,} extra derived words from the frequency list "
          f"({sum(extra.values()):,} lemmas)")

    family_freq = lemma_frequencies(entries, lemmas, freq)

    print("Syllabifying and writing database...")
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        CREATE TABLE words (
            id INTEGER PRIMARY KEY,
            word TEXT NOT NULL UNIQUE,
            hyphenated TEXT NOT NULL,      -- pa-la-bra
            n_syllables INTEGER NOT NULL,
            freq INTEGER NOT NULL,         -- occurrences in OpenSubtitles (0 = unseen)
            lemma_freq INTEGER NOT NULL,   -- lemmas: freq of all its forms; others: freq
            is_lemma INTEGER NOT NULL,     -- 1 = base form (infinitive, singular...)
            source TEXT NOT NULL           -- 'dic', 'lemario' or 'freq'
        );
        CREATE TABLE syllables (
            syllable_plain TEXT NOT NULL,  -- without accents, for searching
            pos INTEGER NOT NULL,          -- 0 = first syllable
            word_id INTEGER NOT NULL REFERENCES words(id),
            syllable TEXT NOT NULL,        -- as written
            PRIMARY KEY (syllable_plain, pos, word_id)
        ) WITHOUT ROWID;
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
    )
    con.executemany("INSERT INTO metadata VALUES (?,?)", DB_METADATA.items())
    word_rows, syl_rows = [], []
    all_words = (
        [(w, w in lemmas, "dic") for w in dict_words]
        + [(w, w in lemmas, "lemario") for w in lemario - dict_words]
        + [(w, is_lemma, "freq") for w, is_lemma in extra.items()]
    )
    all_words.sort()
    for word_id, (w, is_lemma, source) in enumerate(all_words, start=1):
        syls = syllabify(w)
        f = freq.get(w, 0)
        lemma_f = max(family_freq.get(w, 0), f) if is_lemma else f
        word_rows.append(
            (word_id, w, "-".join(syls), len(syls), f, lemma_f, int(is_lemma), source)
        )
        for pos, s in enumerate(syls):
            syl_rows.append((strip_accents(s), pos, word_id, s))
    con.executemany("INSERT INTO words VALUES (?,?,?,?,?,?,?,?)", word_rows)
    con.executemany("INSERT OR IGNORE INTO syllables VALUES (?,?,?,?)", syl_rows)
    con.execute("CREATE INDEX idx_syllables_any ON syllables(syllable_plain, word_id)")
    con.commit()
    con.execute("VACUUM")
    con.close()
    print(f"Done: {len(word_rows):,} words ({sum(r[6] for r in word_rows):,} lemmas), "
          f"{len(syl_rows):,} syllables "
          f"-> {DB_PATH} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    sys.exit(build())
