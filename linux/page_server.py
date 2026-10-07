#!/usr/bin/env python3
"""page_server.py — sers ta page Bobine (vault.html + graph.html) avec un mot de passe.

Pensé pour lire ton vault depuis n'importe où : le petit serveur ne montre QUE
ces deux fichiers (jamais tes fiches, ta config ni ta clé), et demande un mot
de passe. Sur un serveur, on le combine à un tunnel (Cloudflare, Tailscale) :
la page devient une vraie adresse, consultable depuis ton téléphone.

    python3 page_server.py --vault ~/Bobine [--port 8786] [--bind 127.0.0.1]

Le mot de passe : donne-le avec --password, ou mets PAGE_PASSWORD=… dans
config.env (chmod 600 recommandé). Par défaut, le serveur écoute sur
127.0.0.1 (visible de la machine seule) — c'est le tunnel qui expose.

Protection en amont (Cloudflare Access, réseau privé…) : lance avec
--sans-mot-de-passe — la page ne demande plus rien, c'est l'amont qui filtre.

Routes :
    GET /            → vault.html
    GET /vault.html  → vault.html
    GET /graph.html  → graph.html
    GET /health      → ok
    (tout le reste → 404)
"""

import argparse
import base64
import hmac
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FICHIERS = {
    "/": "vault.html",
    "/vault.html": "vault.html",
    "/graph.html": "graph.html",
}

TYPES = {
    "vault.html": "text/html; charset=utf-8",
    "graph.html": "text/html; charset=utf-8",
}


def fichier_demande(chemin):
    """Le nom de fichier autorisé pour ce chemin, ou None (whitelist stricte :
    seuls la page et la carte sont servis, jamais le reste du vault)."""
    chemin = chemin.split("?")[0].split("#")[0]
    return FICHIERS.get(chemin)


def mot_de_passe_de_config(vault, script):
    """Lit PAGE_PASSWORD dans config.env (vault, puis dossier du script)."""
    for dossier in (vault, script):
        fichier = Path(dossier) / "config.env"
        if not fichier.is_file():
            continue
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne.startswith("PAGE_PASSWORD="):
                return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def verifier_auth(entete, mot_de_passe):
    """Vrai si l'en-tête « Basic … » porte le bon mot de passe (temps constant)."""
    if not entete or not entete.startswith("Basic ") or not mot_de_passe:
        return False
    try:
        decode = base64.b64decode(entete[len("Basic "):].strip()).decode("utf-8", errors="ignore")
    except Exception:
        return False
    _, _, fourni = decode.partition(":")
    return hmac.compare_digest(fourni.encode(), mot_de_passe.encode())


def acces_autorise(mot_de_passe, entete):
    """Vrai si la requête peut être servie : pas de mot de passe configuré
    (= protection en amont, ex. Cloudflare Access) ou en-tête Basic valide."""
    if not mot_de_passe:
        return True
    return verifier_auth(entete, mot_de_passe)


class PageHandler(BaseHTTPRequestHandler):
    server_version = "bobine-page/0.1"

    def _entetes(self, code, longueur, type_contenu):
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(longueur))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def _repondre(self, code, texte="", type_contenu="text/plain; charset=utf-8"):
        corps = texte.encode("utf-8")
        self._entetes(code, len(corps), type_contenu)
        self.wfile.write(corps)

    def do_GET(self):
        chemin = self.path.split("?")[0]
        if chemin == "/health":
            self._repondre(200, "ok")
            return

        if not acces_autorise(self.server.mot_de_passe, self.headers.get("Authorization", "")):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Bobine"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        nom = fichier_demande(chemin)
        if not nom:
            self._repondre(404, "inconnu — ici, seuls la page et la carte sont servies.")
            return

        fichier = self.server.vault / nom
        if not fichier.is_file():
            self._repondre(404, nom + " n'existe pas encore — il se génère après ta première fiche.")
            return

        donnees = fichier.read_bytes()
        self._entetes(200, len(donnees), TYPES.get(nom, "text/html; charset=utf-8"))
        self.wfile.write(donnees)


def main():
    ap = argparse.ArgumentParser(description="Bobine — sers ta page (avec mot de passe).")
    ap.add_argument("--vault", default=str(Path(__file__).resolve().parent),
                    help="dossier du vault (défaut : le dossier de ce script)")
    ap.add_argument("--password", default=None,
                    help="mot de passe attendu (défaut : PAGE_PASSWORD de config.env)")
    ap.add_argument("--sans-mot-de-passe", action="store_true",
                    help="ne rien demander (page protégée en amont, ex. Cloudflare Access)")
    ap.add_argument("--port", type=int, default=8786)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    mot_de_passe = args.password or mot_de_passe_de_config(vault, Path(__file__).resolve().parent)
    if args.sans_mot_de_passe:
        mot_de_passe = ""
        print("⚠️  sans mot de passe : la page se sert sans protection propre —")
        print("   garde une protection en amont (ex. Cloudflare Access).")
    elif not mot_de_passe:
        print("Il faut un mot de passe : --password MONMOTDEPASSE, ou PAGE_PASSWORD=… dans config.env,")
        print("— ou --sans-mot-de-passe si la page est protégée en amont (Cloudflare Access).")
        print("Pour en fabriquer un :  openssl rand -hex 16")
        return 1

    serveur = ThreadingHTTPServer((args.bind, args.port), PageHandler)
    serveur.vault = vault
    serveur.mot_de_passe = mot_de_passe
    print("Bobine — ta page : http://%s:%d/  (vault : %s)" % (args.bind, args.port, vault))
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
