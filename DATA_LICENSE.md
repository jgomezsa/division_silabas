# Data licenses

The **code** in this repository is licensed under the [Apache License 2.0](LICENSE).
The repository does **not** contain any third-party data: `build_db.py` downloads
it at build time.

## Data sources

| Source | Author | License | Used for |
| --- | --- | --- | --- |
| [Spanish Hunspell dictionary `es_ES`](https://github.com/LibreOffice/dictionaries/tree/master/es) | RLA-ES project | [GPL-3.0-or-later](https://www.gnu.org/licenses/gpl-3.0.html), [LGPL-3.0-or-later](https://www.gnu.org/licenses/lgpl-3.0.html) or [MPL-1.1-or-later](https://www.mozilla.org/en-US/MPL/1.1/), at the user's choice | word list (forms, conjugations, plurals) |
| [FrequencyWords](https://github.com/hermitdave/FrequencyWords), Spanish 2018 list | Hermit Dave, from the [OpenSubtitles2018](http://opus.nlpl.eu/OpenSubtitles2018.php) corpus (OPUS, www.opensubtitles.org) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | word frequencies and colloquial words |
| [Lemarios](https://github.com/olea/lemarios) | Ismael Olea and contributors | Public domain | lemma list and verb conjugations |

## The generated database

`data/silabas.db` combines the three sources, so it is a derived work of them
and **is not covered by the Apache License**. If you distribute it (or any
other output derived from these sources), it is licensed under the
**[GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html)**:

- The Hunspell dictionary may be used under GPL-3.0.
- CC BY-SA 4.0 adaptations may be licensed under GPL-3.0, which Creative
  Commons [declared compatible](https://creativecommons.org/2015/10/08/cc-by-sa-4-0-now-one-way-compatible-with-gplv3/)
  with BY-SA 4.0.
- Public domain data has no conditions.

When distributing the database, include this file and the attributions above,
and state that it was modified (words were syllabified, filtered and combined).
`build_db.py` also stores the license and attributions in the database's
`metadata` table.

Using the database privately, or running the code to build it, has no extra
conditions.

*This summary is provided for convenience and is not legal advice.*
