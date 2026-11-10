"""Faux Ollama pour tests/e2e : répond en citant le PNJ et le lieu trouvés dans ses consignes, et les note."""
import json, re, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

JOURNAL = sys.argv[1]

class Gestion(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def repondre(self, corps, type_="application/json"):
        self.send_response(200); self.send_header("Content-Type", type_); self.end_headers(); self.wfile.write(corps)
    def do_GET(self):
        self.repondre(b'{"models": []}')
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        system = req["messages"][0]["content"]
        with open(JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps({"system": system, "stop": req["options"].get("stop")}, ensure_ascii=False) + "\n")
        nom = re.search(r"Tu es ([^,]+),", system)[1]
        lieu = re.search(r"Tu te trouves en ce moment ici : ([^.]+)\.", system)
        texte = f"Moi, {nom}, je suis bien à {lieu[1] if lieu else 'nulle part'}, voyageur. Que veux-tu ?"
        lignes = [json.dumps({"message": {"content": m}}).encode() + b"\n" for m in [w + " " for w in texte.split(" ")]]
        self.repondre(b"".join(lignes), "application/x-ndjson")

ThreadingHTTPServer(("127.0.0.1", 5918), Gestion).serve_forever()
