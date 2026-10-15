"""Rule-based syllabification of Spanish words.

Rules (RAE, phonological syllabification):
  * Digraphs ``ch``, ``ll``, ``rr`` are a single consonant. ``qu`` and
    ``gu`` before e/i are a single consonant (the u is silent; ``gü`` is not).
  * Vowel groups: strong vowels (a, e, o and any accented vowel) are separated
    from each other (hiatus); a weak unaccented vowel (i, u, ü, final y) joins
    the adjacent vowels (diphthongs and triphthongs). An accented í/ú forms a
    hiatus with its neighbours (``rí-o``, ``ba-úl``).
  * ``y`` is a consonant before a vowel and a vowel otherwise (``rey``, ``hoy``).
  * ``h`` is treated as a consonant (``a-hu-ma-do``, ``de-sha-cer``).
  * Between two nuclei: one consonant goes to the next syllable; with two or
    more, the last one goes to the next syllable, or the last two if they form
    an inseparable onset (pr, bl, tr, ...).
"""
import re

STRONG = set("aeoáéóàèò")
WEAK = set("iuüy")          # "y" only counts as a vowel when tagged so
STRESSED_WEAK = set("íúìù")  # break any vowel group (rí-o, ba-úl)
VOWELS = STRONG | STRESSED_WEAK | set("iuü")
# Inseparable onsets. "tl" is left out (at-le-ta, as in most of Spain).
ONSETS = {
    "pr", "pl", "br", "bl", "fr", "fl", "tr", "dr", "cr", "cl", "gr", "gl",
    "kr", "kl",
}

_DIGRAPHS = ("ch", "ll", "rr")


def _tokenize(word):
    """Split a word into phoneme-like units, tagging each one as V or C."""
    units = []
    i, n = 0, len(word)
    while i < n:
        c = word[i]
        two = word[i:i + 2]
        if two in _DIGRAPHS:
            units.append([two, "C"])
            i += 2
        elif c in "qg" and i + 2 < n and word[i + 1] == "u" and word[i + 2] in "eéiíè":
            units.append([word[i:i + 2], "C"])
            i += 2
        elif c == "q" and i + 1 < n and word[i + 1] == "u":
            # "qu" before a/o (loanwords like "quórum") still has a silent u
            units.append([two, "C"])
            i += 2
        elif c == "y":
            nxt = word[i + 1] if i + 1 < n else ""
            units.append([c, "C" if nxt in VOWELS else "V"])
            i += 1
        elif c in VOWELS:
            units.append([c, "V"])
            i += 1
        else:
            units.append([c, "C"])
            i += 1
    return units


def _split_vowels(vowels):
    """Split a run of vowels into nuclei (diphthongs, triphthongs, hiatus)."""
    nuclei = [vowels[0]]
    for v in vowels[1:]:
        nucleus = nuclei[-1]
        prev = nucleus[-1]
        if v in STRESSED_WEAK:
            # cuí-da-te, des-truí: weak + stressed weak is still a diphthong
            hiatus = not (prev in WEAK and len(nucleus) == 1)
        elif prev in STRESSED_WEAK:
            hiatus = v not in WEAK
        elif v in STRONG:
            hiatus = any(c in STRONG for c in nucleus)
        else:  # unstressed weak vowel joins the current nucleus
            hiatus = False
        if hiatus:
            nuclei.append(v)
        else:
            nuclei[-1] += v
    return nuclei


def _split_consonants(cons):
    """Return how many consonant units from ``cons`` stay in the coda."""
    if len(cons) <= 1:
        return 0
    last_two = cons[-2] + cons[-1]
    if last_two in ONSETS:
        return len(cons) - 2
    return len(cons) - 1


def syllabify(word):
    """Return the list of syllables of ``word`` (lowercase Spanish)."""
    w = word.lower()
    units = _tokenize(w)

    # Group into: [onset consonants], nucleus, [consonants], nucleus, ...
    # Each element of ``groups`` is ("C", [units]) or ("V", "vowels")
    groups = []
    for text, kind in units:
        if groups and groups[-1][0] == kind:
            groups[-1][1].append(text)
        else:
            groups.append((kind, [text]))

    syllables = []
    current = ""
    for gi, (kind, items) in enumerate(groups):
        if kind == "V":
            nuclei = _split_vowels("".join(items))
            for k, nucleus in enumerate(nuclei):
                if k > 0:
                    syllables.append(current)
                    current = ""
                current += nucleus
        else:
            is_first = gi == 0
            is_last = gi == len(groups) - 1
            if is_first:
                current += "".join(items)
            elif is_last:
                current += "".join(items)
            else:
                coda = _split_consonants(items)
                current += "".join(items[:coda])
                syllables.append(current)
                current = "".join(items[coda:])
    if current:
        syllables.append(current)

    # A word with no vowel (e.g. "sh", "pst") stays as a single "syllable"
    if not any(ch in VOWELS or ch == "y" for ch in w):
        return [w]

    return _fix_prefixes(w, syllables)


def _fix_prefixes(word, syllables):
    """Prefix "sub" before r/l keeps its b: sub-ra-yar, sub-le-var (not su-bli-me)."""
    if (
        len(syllables) > 1
        and word.startswith(("subr", "subl"))
        and not word.startswith("sublim")
        and syllables[0] == "su"
    ):
        return ["sub", syllables[1][1:]] + syllables[2:]
    return syllables


def hyphenate(word):
    return "-".join(syllabify(word))


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        print(hyphenate(arg))
