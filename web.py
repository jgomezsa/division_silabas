"""Local web frontend for find_words.

    python web.py              # opens http://localhost:8000
    python web.py --port 8080 --no-browser
"""
import argparse
import json
import sqlite3
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from build_db import DB_PATH
from find_words import MIN_STARTING, search

MAX_ROWS = 2000  # rows sent to the browser per list; totals are always exact


def find(syllable, exact, all_forms):
    con = sqlite3.connect(DB_PATH)
    try:
        starting = search(con, syllable, True, exact, all_forms)
        containing = None
        if len(starting) < MIN_STARTING:
            containing = search(con, syllable, False, exact, all_forms)
    finally:
        con.close()

    def pack(rows):
        return {"total": len(rows), "rows": rows[:MAX_ROWS]}

    return {
        "syllable": syllable,
        "min_starting": MIN_STARTING,
        "starting": pack(starting),
        "containing": pack(containing) if containing is not None else None,
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        elif url.path == "/api/search":
            qs = parse_qs(url.query)
            syllable = qs.get("q", [""])[0].strip().lower()
            if not syllable or len(syllable) > 10:
                self._send(400, "application/json", b'{"error": "invalid syllable"}')
                return
            result = find(syllable, qs.get("exact") == ["1"], qs.get("all") == ["1"])
            body = json.dumps(result, ensure_ascii=False)
            self._send(200, "application/json; charset=utf-8", body.encode("utf-8"))
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


PAGE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Buscador de sílabas</title>
<style>
  :root {
    --bg: #f7f7f5; --panel: #ffffff; --text: #1d1d1b; --muted: #6b6b66;
    --border: #e2e1dc; --accent: #c2410c; --accent-bg: #fde9dd;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #161615; --panel: #1f1f1d; --text: #ecebe6; --muted: #9a9993;
      --border: #33332f; --accent: #fb923c; --accent-bg: #43281a;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  main { max-width: 860px; margin: 0 auto; padding: 32px 16px 64px; }
  h1 { font-size: 1.6rem; margin: 0 0 4px; }
  .sub { color: var(--muted); margin: 0 0 24px; }
  form { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
  input[type=text] {
    flex: 1 1 240px; font-size: 1.4rem; padding: 10px 14px;
    border: 1px solid var(--border); border-radius: 8px;
    background: var(--panel); color: var(--text);
  }
  input[type=text]:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
  label { color: var(--muted); display: flex; gap: 6px; align-items: center; cursor: pointer; }
  .status { color: var(--muted); margin: 20px 0 8px; min-height: 1.5em; }
  section {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 10px; margin-top: 16px; overflow: hidden;
  }
  section h2 {
    font-size: 1rem; margin: 0; padding: 12px 16px;
    border-bottom: 1px solid var(--border);
  }
  section h2 span { color: var(--muted); font-weight: normal; }
  ul {
    list-style: none; margin: 0; padding: 8px;
    display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 2px 8px;
  }
  li { padding: 4px 8px; border-radius: 6px; display: flex; justify-content: space-between; gap: 8px; }
  li:hover { background: var(--bg); }
  .word { font-weight: 600; }
  .hy { color: var(--muted); font-size: .9rem; white-space: nowrap; }
  .hy b { color: var(--accent); background: var(--accent-bg); border-radius: 3px; padding: 0 2px; font-weight: 600; }
  .more { padding: 8px 16px 14px; }
  button {
    font: inherit; padding: 6px 14px; border-radius: 6px; cursor: pointer;
    border: 1px solid var(--border); background: var(--bg); color: var(--text);
  }
</style>
</head>
<body>
<main>
  <h1>Buscador de sílabas</h1>
  <p class="sub">Palabras que empiezan por una sílaba (o la contienen, si hay menos de 20), ordenadas por frecuencia de uso. Por defecto, verbos en infinitivo y nombres y adjetivos en masculino singular.</p>
  <form id="f" autocomplete="off">
    <input id="q" type="text" placeholder="Escribe una sílaba: pa, tra, ción…" autofocus>
    <label><input id="exact" type="checkbox"> Respetar tildes</label>
    <label><input id="all" type="checkbox"> Incluir conjugaciones y plurales</label>
  </form>
  <div class="status" id="status"></div>
  <div id="out"></div>
</main>
<script>
const PAGE_SIZE = 200;
const $ = id => document.getElementById(id);
const plain = s => s.normalize("NFD").replace(/(?![̃̈])[̀-ͯ]/g, "").normalize("NFC");
let timer, seq = 0;

function esc(s) {
  return s.replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
}

function hyphenated(h, syl, exact, onlyFirst) {
  const target = exact ? syl : plain(syl);
  return h.split("-").map((s, i) => {
    const hit = (exact ? s : plain(s)) === target && (onlyFirst ? i === 0 : i > 0);
    return hit ? `<b>${esc(s)}</b>` : esc(s);
  }).join("-");
}

function renderList(title, data, syl, exact, first) {
  const sec = document.createElement("section");
  const fmt = n => n.toLocaleString("es-ES");
  sec.innerHTML = `<h2>${title} <span>· ${fmt(data.total)} palabras</span></h2><ul></ul>`;
  const ul = sec.querySelector("ul");
  let shown = 0;
  const more = document.createElement("div");
  more.className = "more";
  function page() {
    const rows = data.rows.slice(shown, shown + PAGE_SIZE);
    ul.insertAdjacentHTML("beforeend", rows.map(([w, h, f]) =>
      `<li title="Frecuencia: ${fmt(f)}"><span class="word">${esc(w)}</span>` +
      `<span class="hy">${hyphenated(h, syl, exact, first)}</span></li>`).join(""));
    shown += rows.length;
    const left = data.rows.length - shown;
    more.innerHTML = left > 0 ? `<button>Mostrar ${fmt(Math.min(left, PAGE_SIZE))} más</button>`
      : (data.total > data.rows.length ? `<span class="hy">Se muestran las ${fmt(data.rows.length)} más frecuentes.</span>` : "");
    const b = more.querySelector("button");
    if (b) b.onclick = page;
  }
  page();
  sec.appendChild(more);
  return sec;
}

async function run() {
  const q = $("q").value.trim().toLowerCase();
  const exact = $("exact").checked;
  const all = $("all").checked;
  const my = ++seq;
  if (!q) { $("out").innerHTML = ""; $("status").textContent = ""; return; }
  $("status").textContent = "Buscando…";
  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&exact=${exact ? 1 : 0}&all=${all ? 1 : 0}`);
  if (my !== seq) return;
  if (!res.ok) { $("status").textContent = "Sílaba no válida."; $("out").innerHTML = ""; return; }
  const d = await res.json();
  const out = $("out");
  out.innerHTML = "";
  $("status").textContent = d.starting.total || (d.containing && d.containing.total) ? "" :
    `No se encontraron palabras con «${d.syllable}».`;
  if (d.starting.total || !d.containing)
    out.appendChild(renderList(`Empiezan por «${esc(d.syllable)}»`, d.starting, d.syllable, exact, true));
  if (d.containing && d.containing.total)
    out.appendChild(renderList(`Contienen «${esc(d.syllable)}»`, d.containing, d.syllable, exact, false));
}

$("f").onsubmit = e => { e.preventDefault(); clearTimeout(timer); run(); };
$("q").oninput = () => { clearTimeout(timer); timer = setTimeout(run, 250); };
$("exact").onchange = run;
$("all").onchange = run;
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Web frontend for the syllable search")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if not Path(DB_PATH).exists():
        sys.exit(f"Database not found at {DB_PATH}. Run: python build_db.py")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"Serving on {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
