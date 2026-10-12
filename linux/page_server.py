#!/usr/bin/env python3
"""La page et Demander, sur localhost ou derrière le tunnel déjà protégé.

Mac : page_server.py --vault ~/Bobine --local (127.0.0.1 exclusivement).
Serveur : PAGE_PASSWORD existant ; PAGE_ORIGIN=https://bobine.exemple.fr pour
activer Demander sur l'adresse publique. Sans origine publique, lecture seule.
Seuls les deux HTML et les routes explicites ci-dessous sont servis.
Le jeton de protection est créé en mémoire au démarrage, jamais dans un HTML.
"""

import argparse
import base64
import collections
import fcntl
import hashlib
import hmac
import json
import math
import os
import secrets
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import demander
from enrichir import FICHIER_PROFIL, TAILLE_MAX_PROFIL, charger_config, empreinte_profil, lire_profil, resoudre_fournisseur

FICHIERS = {"/": "vault.html", "/vault.html": "vault.html", "/graph.html": "graph.html"}
TYPES = {nom: "text/html; charset=utf-8" for nom in FICHIERS.values()}
MAX_CORPS = 32768
MAX_CONNEXIONS = 12
DELAI_ENTREE = 10
DELAI_DEMANDE = 60
MAX_PAR_MINUTE = 10
MAX_PAR_JOUR = 100
FICHIER_COMPTEUR = ".bobine-demandes.json"
MAX_CORPS_PROFIL = 16384
DELAI_PAGE = 90
# Même en-tête que celui écrit par l'installation : des explications, jamais lues.
ENTETE_PROFIL = (
    "# Ton profil Bobine (facultatif).\n"
    "# Écris quelques lignes sur toi : ce que tu fais, ce que tu cherches dans tes vidéos.\n"
    "# Bobine s'en sert pour le bloc « Pour toi » de chaque fiche.\n"
    "# Les lignes qui commencent par # sont des explications : elles ne sont jamais lues.\n"
    "# Ce texte est envoyé à ton service d'IA avec les demandes de résumé : évite les informations sensibles.\n"
    "\n"
)


class ErreurProfil(Exception):
    def __init__(self, statut, message, code):
        super().__init__(message)
        self.statut, self.message, self.code = statut, message, code


def version_profil(vault):
    """Empreinte du fichier tel qu'il est sur le disque : détecte une modification
    faite ailleurs (fichier, autre onglet) entre la lecture et l'enregistrement."""
    chemin = Path(vault) / FICHIER_PROFIL
    try:
        fd = os.open(chemin, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return ""
    except OSError:
        raise ErreurProfil(503, "Ton profil n'est pas lisible pour le moment.", "profil_illisible") from None
    with os.fdopen(fd, "rb") as flux:
        infos = os.fstat(flux.fileno())
        if not stat.S_ISREG(infos.st_mode) or infos.st_size > 65536:
            raise ErreurProfil(503, "Ton profil n'est pas lisible pour le moment.", "profil_illisible")
        return hashlib.sha256(flux.read(65537)).hexdigest()[:20]


def texte_profil_valide(texte):
    """Texte propre, ou ErreurProfil avec un message simple."""
    if not isinstance(texte, str):
        raise ErreurProfil(400, "Le profil n'est pas lisible.", "profil_invalide")
    texte = texte.replace("\r\n", "\n").replace("\r", "\n")
    if any((ord(c) < 32 and c not in "\n\t") or ord(c) == 127 for c in texte):
        raise ErreurProfil(400, "Le profil contient des caractères invisibles. Retire-les puis réessaie.",
                           "profil_invalide")
    lignes = [ligne.rstrip() for ligne in texte.split("\n")]
    if any(ligne.lstrip().startswith("#") for ligne in lignes):
        raise ErreurProfil(400, "Une ligne qui commence par # serait ignorée par Bobine. "
                           "Retire ce # ou place-le plus loin dans la phrase.", "profil_diese")
    texte = "\n".join(lignes).strip()
    if len(texte) > TAILLE_MAX_PROFIL:
        raise ErreurProfil(400, "Ton profil est trop long : garde l'essentiel en "
                           + str(TAILLE_MAX_PROFIL) + " caractères maximum.", "profil_trop_long")
    return texte


def ecrire_profil(vault, texte):
    """Écriture atomique en 600 ; jamais à travers un lien ou un fichier spécial."""
    chemin = Path(vault) / FICHIER_PROFIL
    try:
        infos = os.lstat(chemin)
        if not stat.S_ISREG(infos.st_mode) or infos.st_nlink != 1:
            raise ErreurProfil(409, "Ton profil est un fichier particulier : modifie-le directement "
                               "dans le dossier Bobine.", "profil_special")
    except FileNotFoundError:
        pass
    fd, temporaire = tempfile.mkstemp(prefix=".bobine-profil-", dir=str(chemin.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as flux:
            flux.write(ENTETE_PROFIL + (texte + "\n" if texte else ""))
            flux.flush()
            os.fsync(flux.fileno())
        os.replace(temporaire, chemin)
    finally:
        if os.path.exists(temporaire):
            os.unlink(temporaire)


def regenerer_page(vault):
    """Page refaite tout de suite, gratuitement (aucun appel IA). Vrai si réussi."""
    script = Path(__file__).with_name("generate_page.py")
    if not script.is_file():
        return False
    try:
        fin = subprocess.run([sys.executable, str(script), "--vault", str(vault)],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, timeout=DELAI_PAGE, cwd=str(script.parent))
        return fin.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False



def fichier_demande(chemin):
    return FICHIERS.get(chemin.split("?")[0].split("#")[0])


def mot_de_passe_de_config(vault, script):
    return charger_config(script, vault).get("PAGE_PASSWORD", "")


def verifier_auth(entete, mot_de_passe):
    if not entete or not entete.startswith("Basic ") or not mot_de_passe:
        return False
    try:
        decode = base64.b64decode(entete[6:], validate=True).decode("utf-8")
    except (ValueError, UnicodeError):
        return False
    _, separateur, fourni = decode.partition(":")
    return bool(separateur) and hmac.compare_digest(fourni.encode(), mot_de_passe.encode())


def acces_autorise(mot_de_passe, entete):
    return not mot_de_passe or verifier_auth(entete, mot_de_passe)


def origine_valide(valeur):
    """Origine exacte, sans chemin ni identifiants, jamais un en-tête réfléchi."""
    if not isinstance(valeur, str) or not valeur or any(ord(c) <= 32 or ord(c) >= 127 for c in valeur):
        return None
    try:
        u = urlsplit(valeur)
        if (u.scheme not in ("http", "https") or not u.hostname or u.username is not None
                or u.password is not None or u.path or u.query or u.fragment or "\\" in valeur):
            return None
        port = u.port
        if port is not None and not 1 <= port <= 65535:
            return None
        hote = u.hostname.lower()
        if ":" in hote:
            hote = "[" + hote + "]"
        if port and port != (443 if u.scheme == "https" else 80):
            hote += ":" + str(port)
        return u.scheme + "://" + hote
    except ValueError:
        return None


class Compteur:
    """Quota par installation, persistant même après redémarrage, sans conversation.

    Le verrou du chat sérialise les accès. Seuls des horodatages sont enregistrés.
    Un fichier invalide bloque les nouveaux appels plutôt que remettre le quota à zéro.
    """

    def __init__(self, vault):
        self.chemin = Path(vault) / FICHIER_COMPTEUR

    def reserver(self, maintenant=None):
        # Mac et Linux : verrou entre processus, pas seulement entre threads.
        verrou = self.chemin.with_suffix(".lock")
        fd = os.open(verrou, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
                raise ValueError("verrou non régulier")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self._reserver_verrouille(maintenant)
        finally:
            os.close(fd)

    def _reserver_verrouille(self, maintenant=None):
        maintenant = time.time() if maintenant is None else maintenant
        ancien = []
        try:
            fd = os.open(self.chemin, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            fd = None
        if fd is not None:
            with os.fdopen(fd, "r", encoding="utf-8") as flux:
                infos = os.fstat(flux.fileno())
                if not stat.S_ISREG(infos.st_mode) or infos.st_size > 32768 or infos.st_nlink != 1:
                    raise ValueError("compteur non régulier")
                ancien = json.loads(flux.read(32769))
            if (not isinstance(ancien, list) or len(ancien) > MAX_PAR_JOUR
                    or any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in ancien)):
                raise ValueError("compteur illisible")
        recent = [t for t in ancien if t > maintenant - 86400]
        if len(recent) >= MAX_PAR_JOUR:
            return "jour"
        if sum(t > maintenant - 60 for t in recent) >= MAX_PAR_MINUTE:
            return "minute"
        fd, temporaire = tempfile.mkstemp(prefix=".bobine-compteur-", dir=self.chemin.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as flux:
                json.dump(recent + [maintenant], flux)
                flux.flush()
                os.fsync(flux.fileno())
            os.replace(temporaire, self.chemin)
        finally:
            if os.path.exists(temporaire):
                os.unlink(temporaire)
        return None


def repondre_borne(vault, question, historique=None, fiche=None):
    """Un enfant sans shell : délai mural couvrant DNS, TLS, en-têtes et corps.

    Ni clé ni question dans les arguments système. La demande passe par stdin,
    la configuration est lue par l'enfant. Aucun fichier temporaire de dialogue.
    Un fournisseur bloqué est interrompu, pas laissé en travail de fond.
    """
    entree = json.dumps({"vault": str(vault), "question": question, "historique": historique or [],
                         "fiche": fiche}, ensure_ascii=False).encode("utf-8")
    processus = subprocess.Popen([sys.executable, str(Path(__file__).with_name("demander.py")), "--interne"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        sortie, _ = processus.communicate(entree, timeout=DELAI_DEMANDE)
    except subprocess.TimeoutExpired:
        processus.kill()
        processus.communicate()
        raise demander.ErreurDemande("Le service met trop de temps à répondre. Réessaie plus tard.",
                                    "delai_depasse") from None
    if len(sortie) > 65536:
        raise demander.ErreurDemande("La réponse reçue est trop longue.", "reponse_invalide")
    try:
        resultat = json.loads(sortie.decode("utf-8"))
        if not isinstance(resultat, dict):
            raise ValueError()
        if "erreur" in resultat and isinstance(resultat["erreur"], str):
            raise demander.ErreurDemande(resultat["erreur"][:500], resultat.get("code", "indisponible"))
        if (processus.returncode != 0 or not isinstance(resultat.get("reponse"), str)
                or not isinstance(resultat.get("sources"), list)):
            raise ValueError()
        return resultat
    except (UnicodeError, ValueError):
        raise demander.ErreurDemande("La réponse reçue n'est pas lisible.", "reponse_invalide") from None


class ServeurBobine(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, adresse, vault, mot_de_passe="", local=False, origine="", amont=False):
        if local and adresse[0] != "127.0.0.1":
            raise ValueError("Le serveur local doit écouter sur 127.0.0.1.")
        if not local and not mot_de_passe and not amont:
            raise ValueError("Un mot de passe ou une protection en amont est nécessaire.")
        publique = origine_valide(origine) if origine else None
        if origine and (not publique or not publique.startswith("https://")):
            raise ValueError("PAGE_ORIGIN doit être une origine HTTPS sans chemin.")
        if local and origine:
            raise ValueError("Le mode local ne prend pas d'origine publique.")
        self.vault = Path(vault).resolve()
        self.mot_de_passe = mot_de_passe if not local else ""
        self.local = local
        self.origine_publique = publique
        self.jeton = secrets.token_urlsafe(32)
        self.occupe = threading.Lock()
        self.profil_verrou = threading.Lock()
        self.connexions = threading.BoundedSemaphore(MAX_CONNEXIONS)
        self.compteur = Compteur(self.vault)
        self.admissions = collections.deque(maxlen=120)
        self.verrou_admissions = threading.Lock()
        super().__init__(adresse, PageHandler)
        port = self.server_address[1]
        self.origines = {"http://127.0.0.1:" + str(port), "http://localhost:" + str(port)}
        if publique:
            self.origines.add(publique)

    def process_request(self, request, client_address):
        # Borne aussi les connexions avant authentification et avant lecture du corps.
        if not self.connexions.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.connexions.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connexions.release()

    def handle_error(self, request, client_address):
        # Pas de traceback contenant des données utilisateur dans les journaux.
        pass

    def admettre_api(self):
        with self.verrou_admissions:
            maintenant = time.monotonic()
            while self.admissions and self.admissions[0] <= maintenant - 60:
                self.admissions.popleft()
            if len(self.admissions) >= 120:
                return False
            self.admissions.append(maintenant)
            return True

    def disponible(self):
        try:
            cfg = charger_config(Path(__file__).resolve().parent, self.vault)
            cle, adresse, modele = resoudre_fournisseur(cfg)
            return bool(cle and adresse and modele)
        except (OSError, ValueError):
            return False


class PageHandler(BaseHTTPRequestHandler):
    server_version = "bobine-page/0.2"
    sys_version = ""
    timeout = 10

    def setup(self):
        super().setup()
        # Échéance absolue : envoyer un octet à la fois ne prolonge pas le délai.
        self.fin_lecture = threading.Event()
        self.garde_entree = threading.Timer(DELAI_ENTREE, self._couper_entree)
        self.garde_entree.daemon = True
        self.garde_entree.start()

    def _couper_entree(self):
        if self.fin_lecture.is_set():
            return
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _entree_finie(self):
        self.fin_lecture.set()
        self.garde_entree.cancel()

    def finish(self):
        self._entree_finie()
        super().finish()

    def log_message(self, format, *args):
        # Ni questions, ni jetons, ni URLs avec leurs paramètres dans les logs.
        pass

    def _unique(self, nom):
        valeurs = self.headers.get_all(nom, [])
        return valeurs[0] if len(valeurs) == 1 else None

    def _repondre(self, code, corps=b"", type_contenu="application/json; charset=utf-8", entetes=None):
        if isinstance(corps, str):
            corps = corps.encode("utf-8")
        self.send_response(code)
        for nom, valeur in {"Content-Type": type_contenu, "Content-Length": str(len(corps)),
                            "Cache-Control": "no-store", "X-Robots-Tag": "noindex",
                            "X-Content-Type-Options": "nosniff",
                            # same-origin, pas no-referrer : sous Safari (WebKit), no-referrer
                            # fait partir les POST avec Origin: null, refusés par le contrôle
                            # d'origine. Rien n'est transmis aux autres sites dans les deux cas.
                            "Referrer-Policy": "same-origin",
                            "X-Frame-Options": "DENY", "Connection": "close"}.items():
            self.send_header(nom, valeur)
        for nom, valeur in (entetes or {}).items():
            self.send_header(nom, valeur)
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(corps)
        except (OSError, socket.timeout):
            pass

    def _json(self, code, donnees, entetes=None):
        self._repondre(code, json.dumps(donnees, ensure_ascii=False).encode("utf-8"), entetes=entetes)

    def _erreur(self, statut, message, code, entetes=None):
        self._json(statut, {"erreur": message, "code": code}, entetes)

    def _auth(self):
        if not acces_autorise(self.server.mot_de_passe, self._unique("Authorization") or ""):
            self._erreur(401, "Reconnecte-toi à Bobine pour continuer.", "authentification",
                         {"WWW-Authenticate": 'Basic realm="Bobine"'})
            return False
        return True

    def _origines_hote(self):
        hote = self._unique("Host")
        if not hote:
            return set()
        # Ne jamais faire confiance à X-Forwarded-Host/Proto : origine publique configurée.
        return {o for o in self.server.origines if urlsplit(o).netloc == hote.lower()}

    def _hote_page(self):
        # Compatibilité lecture seule des anciens tunnels avant ajout de PAGE_ORIGIN.
        return bool(self._origines_hote()) or (not self.server.local and not self.server.origine_publique)

    def _origine_api(self, post=False):
        autorisees = self._origines_hote()
        site = self._unique("Sec-Fetch-Site")
        origine = self._unique("Origin")
        if (not autorisees or len(self.headers.get_all("Origin", [])) > 1
                or len(self.headers.get_all("Sec-Fetch-Site", [])) > 1):
            return False
        if site is not None and site not in (("same-origin",) if post else ("same-origin", "none")):
            return False
        if post or origine is not None:
            return bool(origine_valide(origine) in autorisees)
        return True

    def do_GET(self):
        self._entree_finie()
        chemin = self.path.split("?")[0]
        if not self._hote_page():
            self._erreur(403, "Cette adresse n'est pas autorisée.", "adresse_refusee")
            return
        # Route historique de supervision, sans données privées.
        if chemin == "/health":
            self._repondre(200, "ok", "text/plain; charset=utf-8")
            return
        if not self._auth():
            return
        if chemin == "/api/bobine":
            if not self._origine_api():
                self._erreur(403, "Ouvre Bobine depuis son adresse habituelle.", "origine_refusee")
                return
            if not self.server.admettre_api():
                self._erreur(429, "Patiente un instant avant de réessayer.", "limite", {"Retry-After": "60"})
                return
            disponible = self.server.disponible()
            # Le jeton protège aussi le profil, qui fonctionne sans clé API.
            self._json(200, {"disponible": disponible, "profil": True, "jeton": self.server.jeton})
            return
        if chemin == "/api/profil":
            if not self._origine_api():
                self._erreur(403, "Ouvre Bobine depuis son adresse habituelle.", "origine_refusee")
                return
            if not self.server.admettre_api():
                self._erreur(429, "Patiente un instant avant de réessayer.", "limite", {"Retry-After": "60"})
                return
            try:
                with self.server.profil_verrou:
                    self._json(200, {"texte": lire_profil(self.server.vault),
                                     "version": version_profil(self.server.vault),
                                     "max": TAILLE_MAX_PROFIL})
            except ErreurProfil as erreur:
                self._erreur(erreur.statut, erreur.message, erreur.code)
            return
        nom = fichier_demande(self.path)
        if not nom:
            self._erreur(404, "Cette page n'existe pas.", "introuvable")
            return
        fichier = self.server.vault / nom
        try:
            if fichier.is_symlink() or not fichier.is_file():
                raise OSError()
            donnees = fichier.read_bytes()
        except OSError:
            self._erreur(404, "Ta page sera disponible après la première vidéo.", "page_absente")
            return
        self._repondre(200, donnees, TYPES[nom])

    def do_OPTIONS(self):
        # Aucun accès intersite, aucune réponse Access-Control-Allow-*.
        self._erreur(403, "Les demandes depuis un autre site sont refusées.", "origine_refusee")

    def do_POST(self):
        if not self._auth():
            return
        if self.path not in ("/api/demander", "/api/profil"):
            self._erreur(404, "Cette action n'existe pas.", "introuvable")
            return
        jeton = self._unique("X-Bobine-Token") or ""
        if (not self._origine_api(post=True)
                or not hmac.compare_digest(jeton.encode("utf-8"), self.server.jeton.encode("utf-8"))):
            self._erreur(403, "Recharge la page Bobine avant de réessayer.", "origine_refusee")
            return
        if not self.server.admettre_api():
            self._erreur(429, "Patiente un instant avant de réessayer.", "limite", {"Retry-After": "60"})
            return
        type_corps = self._unique("Content-Type") or ""
        longueur = self._unique("Content-Length")
        if self.headers.get_all("Transfer-Encoding") or self.headers.get_all("Content-Encoding"):
            self._erreur(400, "Le format de la demande n'est pas accepté.", "format_invalide")
            return
        if type_corps.lower() not in ("application/json", "application/json; charset=utf-8"):
            self._erreur(415, "Le format de la demande n'est pas accepté.", "format_invalide")
            return
        if not longueur or not longueur.isascii() or not longueur.isdecimal() or len(longueur) > 8:
            self._erreur(411, "La demande est incomplète.", "longueur_absente")
            return
        taille = int(longueur)
        if self.path == "/api/profil":
            self._post_profil(taille)
            return
        if not 1 <= taille <= MAX_CORPS:
            self._erreur(413, "Cette demande est trop longue. Raccourcis ta question.", "demande_trop_longue")
            return
        if not self.server.disponible():
            self._erreur(503, "Le service de réponse n'est pas configuré.", "indisponible")
            return
        try:
            brut = self.rfile.read(taille)
            if len(brut) != taille:
                raise ValueError()
            donnees = json.loads(brut.decode("utf-8"))
            if not isinstance(donnees, dict) or set(donnees) - {"question", "historique", "fiche"}:
                raise ValueError()
            question = donnees.get("question")
            if not isinstance(question, str) or not question.strip() or len(question) > demander.MAX_CARACTERES_QUESTION:
                raise ValueError()
            historique = demander._historique(donnees.get("historique"))
            fiche = donnees.get("fiche")
            if fiche is not None and (not isinstance(fiche, str) or not demander.MOTIF_ID.fullmatch(fiche)):
                raise ValueError()
        except socket.timeout:
            self._erreur(408, "La demande a pris trop de temps. Réessaie.", "delai_depasse")
            return
        except (ValueError, UnicodeError, RecursionError, demander.ErreurDemande):
            self._erreur(400, "La question n'est pas lisible ou est trop longue.", "demande_invalide")
            return
        finally:
            self._entree_finie()
        if not self.server.occupe.acquire(blocking=False):
            self._erreur(409, "Bobine prépare déjà une réponse. Réessaie dans un instant.", "occupe")
            return
        verrou_fichier = None
        try:
            try:
                verrou_fichier = os.open(self.server.vault / ".bobine-chat.lock",
                                         os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
                infos = os.fstat(verrou_fichier)
                if not stat.S_ISREG(infos.st_mode) or infos.st_nlink != 1:
                    raise OSError("verrou non régulier")
                fcntl.flock(verrou_fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self._erreur(409, "Bobine prépare déjà une réponse. Réessaie dans un instant.", "occupe")
                return
            except OSError:
                self._erreur(503, "Bobine ne peut pas préparer de réponse pour le moment.", "indisponible")
                return
            try:
                limite = self.server.compteur.reserver()
            except (OSError, ValueError):
                self._erreur(503, "Le compteur de demandes doit être vérifié avant de continuer.", "compteur_indisponible")
                return
            if limite:
                texte = ("La limite quotidienne est atteinte. Réessaie demain." if limite == "jour"
                         else "Tu as posé plusieurs questions rapidement. Patiente une minute.")
                self._erreur(429, texte, "limite", {"Retry-After": "86400" if limite == "jour" else "60"})
                return
            try:
                reponse = repondre_borne(self.server.vault, question, historique=historique, fiche=fiche)
            except demander.ErreurDemande as erreur:
                statut = (400 if erreur.code in {"fiche_introuvable", "fiche_invalide", "question_invalide", "historique_invalide"}
                          else 504 if erreur.code == "delai_depasse" else 502)
                self._erreur(statut, erreur.message, erreur.code)
                return
            except Exception:
                self._erreur(503, "Bobine n'a pas pu répondre. Réessaie dans un instant.", "indisponible")
                return
            self._json(200, reponse)
        finally:
            if verrou_fichier is not None:
                os.close(verrou_fichier)
            self.server.occupe.release()


def _post_profil_methode(self, taille):
    """Enregistre Mon profil.txt : corps lu et validé avant tout verrou ou écriture."""
    if not 1 <= taille <= MAX_CORPS_PROFIL:
        self._entree_finie()
        self._erreur(413, "Ton profil est trop long.", "profil_trop_long")
        return
    try:
        brut = self.rfile.read(taille)
        if len(brut) != taille:
            raise ValueError()
        donnees = json.loads(brut.decode("utf-8"))
        if (not isinstance(donnees, dict) or set(donnees) != {"texte", "version"}
                or not isinstance(donnees["version"], str) or len(donnees["version"]) > 64):
            raise ValueError()
        texte = texte_profil_valide(donnees["texte"])
    except socket.timeout:
        self._erreur(408, "L'enregistrement a pris trop de temps. Réessaie.", "delai_depasse")
        return
    except ErreurProfil as erreur:
        self._erreur(erreur.statut, erreur.message, erreur.code)
        return
    except (ValueError, UnicodeError, RecursionError):
        self._erreur(400, "Le profil n'est pas lisible.", "profil_invalide")
        return
    finally:
        self._entree_finie()
    if not self.server.profil_verrou.acquire(blocking=False):
        self._erreur(409, "Un enregistrement est déjà en cours. Réessaie dans un instant.", "occupe")
        return
    verrou = None
    try:
        try:
            verrou = os.open(self.server.vault / ".bobine-profil.lock",
                             os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            infos = os.fstat(verrou)
            if not stat.S_ISREG(infos.st_mode) or infos.st_nlink != 1:
                raise OSError("verrou non régulier")
            fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._erreur(409, "Un enregistrement est déjà en cours. Réessaie dans un instant.", "occupe")
            return
        except OSError:
            self._erreur(503, "Ton profil ne peut pas être enregistré pour le moment.", "indisponible")
            return
        try:
            if not hmac.compare_digest(version_profil(self.server.vault).encode(), donnees["version"].encode()):
                raise ErreurProfil(409, "Ton profil a été modifié ailleurs. Recharge la page pour voir "
                                   "la dernière version : ton texte reste dans le champ.", "profil_modifie")
            ecrire_profil(self.server.vault, texte)
            version = version_profil(self.server.vault)
        except ErreurProfil as erreur:
            self._erreur(erreur.statut, erreur.message, erreur.code)
            return
        except OSError:
            self._erreur(503, "Ton profil ne peut pas être enregistré pour le moment.", "indisponible")
            return
        page = regenerer_page(self.server.vault)
        self._json(200, {"texte": lire_profil(self.server.vault), "version": version,
                         "empreinte": empreinte_profil(lire_profil(self.server.vault)),
                         "page_actualisee": page})
    finally:
        if verrou is not None:
            os.close(verrou)
        self.server.profil_verrou.release()


PageHandler._post_profil = _post_profil_methode


def main():
    ap = argparse.ArgumentParser(description="Bobine : ta page et tes questions, chez toi.")
    ap.add_argument("--vault", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--password", default=None)
    ap.add_argument("--sans-mot-de-passe", action="store_true")
    ap.add_argument("--local", action="store_true", help="Mac : écoute exclusivement sur 127.0.0.1")
    ap.add_argument("--port", type=int, default=8786)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()
    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        print("Le dossier Bobine n'existe pas.")
        return 1
    try:
        cfg = charger_config(Path(__file__).resolve().parent, vault)
        mdp = args.password or cfg.get("PAGE_PASSWORD", "")
        if args.sans_mot_de_passe:
            mdp = ""
        serveur = ServeurBobine((args.bind, args.port), vault, mdp, local=args.local,
                                origine="" if args.local else cfg.get("PAGE_ORIGIN", ""),
                                amont=args.sans_mot_de_passe)
    except (ValueError, OSError) as erreur:
        print("La page n'a pas pu démarrer. Vérifie son adresse, son port et sa protection.")
        if isinstance(erreur, ValueError):
            print(str(erreur))
        return 1
    if args.sans_mot_de_passe and not args.local:
        print("Protection en amont requise : garde ton contrôle d'accès devant le serveur.")
    if not args.local and not serveur.origine_publique:
        print("Lecture disponible. Pour Demander à distance, renseigne PAGE_ORIGIN dans config.env.")
    print("Bobine : la page est prête sur le port " + str(serveur.server_address[1]) + ".")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
