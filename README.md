# silabas_es

Find Spanish words by syllable. Lists words whose **first syllable** matches; if
there are fewer than 20, it also lists words **containing** the syllable in any
other position. By default only base forms are listed: verbs in infinitive,
nouns and adjectives in masculine singular (no conjugations, plurals or
feminines). Results are ordered by frequency of use. Standard library only.

```
python build_db.py          # once: downloads sources, builds data/silabas.db (~1-2 min)
python find_words.py pa
python find_words.py ción --limit 0     # all results
python find_words.py cion --exact       # accents must match (default: ignored)
python find_words.py tra --plain        # just the words
python find_words.py pa --all-forms     # also conjugations, plurals, feminines
python web.py                           # web frontend at http://localhost:8000
```

## Data

| Source | Use |
| --- | --- |
| [LibreOffice `es_ES` Hunspell dictionary](https://github.com/LibreOffice/dictionaries/tree/master/es) (RLA-ES, Spain variant, GPL/LGPL/MPL) | ~659k word forms after expanding affix rules (conjugations, plurals, enclitics) |
| [olea/lemarios](https://github.com/olea/lemarios) (public domain) | general lemma list (88k) and verb conjugations, to tell base forms from inflected ones |
| [OpenSubtitles 2018 frequency list](https://github.com/hermitdave/FrequencyWords) (CC-BY-SA 4.0) | word frequency for ranking, plus ~14k colloquial words derived from dictionary words (*gatito*, *grandote*, *pásame*) |

Words are syllabified by rules (`syllabify.py`) and stored in SQLite:
`words(word, hyphenated, freq, lemma_freq, is_lemma, source)` and
`syllables(syllable_plain, pos, word_id, syllable)`, indexed by syllable and position.
`lemma_freq` is the frequency of all the forms of a lemma (*estar*: *está*, *estoy*...),
used to rank base forms.

## Files

- `hunspell_expand.py`: expands Hunspell `.dic` + `.aff` into every word form
- `syllabify.py`: Spanish syllabification (`python syllabify.py canción` → `can-ción`)
- `build_db.py`: downloads the sources and builds the database
- `find_words.py`: search CLI
- `web.py`: local web frontend (same search, served with `http.server`)
