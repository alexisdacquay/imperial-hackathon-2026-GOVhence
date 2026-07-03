"""Loopback-only static server for the GOVhence audit console.

Why this exists instead of `python -m http.server`: a bare http.server binds to
ALL network interfaces and serves the WHOLE directory it is started in. Run from
team-one/, that would expose `.env` (live API keys) and `data/cocoshamem.json`
(the full ungated memory store) to every device on the Wi-Fi — a total bypass of
the very gate this project enforces. This server instead:

  - binds to 127.0.0.1 only (never reachable from the LAN), and
  - serves ONLY an allow-list of paths: the GUI files and data/events.jsonl (the
    console's activity feed). Everything else -> 404. So .env, users.json, and the
    memory store are never served, even by direct URL.

Run from team-one/:  <python> GUI/serve_gui.py   ·   http://127.0.0.1:8777
"""
import http.server
import posixpath
from pathlib import Path
from urllib.parse import unquote, urlparse

_TEAM = Path(__file__).resolve().parent.parent          # team-one/
HOST, PORT = "127.0.0.1", 8777

# Exactly what the console needs — nothing under data/ except the events feed,
# and nothing outside GUI/ at all.
_ALLOWED_FILES = {"data/events.jsonl"}
_ALLOWED_PREFIXES = ("GUI/",)


def _is_allowed(rel):
    return rel in _ALLOWED_FILES or any(rel.startswith(p) for p in _ALLOWED_PREFIXES)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(_TEAM), **kw)

    def _rel(self):
        # normalised, repo-relative path with no traversal, leading slash stripped
        path = posixpath.normpath(unquote(urlparse(self.path).path)).lstrip("/")
        return "" if path == "." else path

    def translate_path(self, path):
        # Only ever resolve inside team-one/, and only for allow-listed paths.
        if not _is_allowed(self._rel()):
            return str(_TEAM / "__forbidden__")     # nonexistent -> 404
        return super().translate_path(path)

    def send_head(self):
        if not _is_allowed(self._rel()):
            self.send_error(404, "Not served")      # .env / store / users.json etc.
            return None
        return super().send_head()

    def log_message(self, *a):
        pass                                        # quiet


def main():
    with http.server.ThreadingHTTPServer((HOST, PORT), Handler) as srv:
        print(f"GOVhence console — loopback only at http://{HOST}:{PORT}/GUI/"
              f"GOVhence%20Audit%20Console.dc.html")
        print("Serving GUI/ + data/events.jsonl only (never .env or the store). Ctrl-C to stop.")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")


if __name__ == "__main__":
    main()
