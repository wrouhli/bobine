#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests de page_server.py — whitelist des fichiers, lecture du mot de passe, auth Basic.

Lancement (aucune dépendance à installer) :

    python3 -m unittest discover -s tests
"""

import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import page_server  # noqa: E402


class FichierDemande(unittest.TestCase):
    """fichier_demande : whitelist stricte (page et carte uniquement)."""

    def test_routes_autorisees(self):
        self.assertEqual(page_server.fichier_demande("/"), "vault.html")
        self.assertEqual(page_server.fichier_demande("/vault.html"), "vault.html")
        self.assertEqual(page_server.fichier_demande("/graph.html"), "graph.html")

    def test_query_et_fragment_ignores(self):
        self.assertEqual(page_server.fichier_demande("/graph.html?x=1"), "graph.html")
        self.assertEqual(page_server.fichier_demande("/vault.html#top"), "vault.html")

    def test_tout_le_reste_refuse(self):
        for chemin in ("/config.env", "/../config.env", "/raw/yt_abc.md",
                       "/journal.json", "/index.md", "/.inbox-local.txt",
                       "/systemd/bobine-watch.service"):
            self.assertIsNone(page_server.fichier_demande(chemin), chemin)


class Auth(unittest.TestCase):
    """verifier_auth : en-tête Basic, comparaison stricte."""

    def entete(self, identifiant, motdepasse):
        brut = ("%s:%s" % (identifiant, motdepasse)).encode()
        return "Basic " + base64.b64encode(brut).decode()

    def test_bon_mot_de_passe(self):
        self.assertTrue(page_server.verifier_auth(self.entete("bobine", "abc123"), "abc123"))
        self.assertTrue(page_server.verifier_auth(self.entete("", "abc123"), "abc123"))

    def test_mauvais_mot_de_passe(self):
        self.assertFalse(page_server.verifier_auth(self.entete("bobine", "abcd"), "abc123"))

    def test_entetes_invalides(self):
        for entete in ("", "Bearer xyz", "Basic ???!!!"):
            self.assertFalse(page_server.verifier_auth(entete, "abc123"), entete)

    def test_sans_mot_de_passe_configure(self):
        self.assertFalse(page_server.verifier_auth(self.entete("a", "b"), ""))


class ConfigMotDePasse(unittest.TestCase):
    """mot_de_passe_de_config : lecture de PAGE_PASSWORD dans config.env."""

    def test_lit_le_mot_de_passe(self):
        with tempfile.TemporaryDirectory() as dossier:
            (Path(dossier) / "config.env").write_text(
                '# commentaire\nNOM="Mon Bobine"\nPAGE_PASSWORD="secret-42"\n',
                encoding="utf-8")
            trouve = page_server.mot_de_passe_de_config(Path(dossier), Path(dossier))
        self.assertEqual(trouve, "secret-42")

    def test_absent(self):
        with tempfile.TemporaryDirectory() as dossier:
            self.assertEqual(page_server.mot_de_passe_de_config(Path(dossier), Path(dossier)), "")


class AccesAutorise(unittest.TestCase):
    """acces_autorise : sans mot de passe (protection en amont) ou Basic valide."""

    def entete(self, identifiant, motdepasse):
        brut = ("%s:%s" % (identifiant, motdepasse)).encode()
        return "Basic " + base64.b64encode(brut).decode()

    def test_sans_mot_de_passe_configure(self):
        self.assertTrue(page_server.acces_autorise("", ""))
        self.assertTrue(page_server.acces_autorise("", self.entete("a", "b")))

    def test_avec_mot_de_passe(self):
        self.assertTrue(page_server.acces_autorise("abc123", self.entete("bobine", "abc123")))
        self.assertFalse(page_server.acces_autorise("abc123", ""))
        self.assertFalse(page_server.acces_autorise("abc123", self.entete("bobine", "mauvais")))



class ServeurDemander(unittest.TestCase):
    """Vraies requêtes HTTP, fournisseur entièrement simulé, y compris un tunnel public."""

    def setUp(self):
        import os
        from unittest import mock
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Chemin réel : le serveur résout son dossier (macOS : /var -> /private/var).
        self.vault = Path(self.tmp.name).resolve()
        (self.vault / "vault.html").write_text("<html>Bibliothèque fictive</html>", encoding="utf-8")
        (self.vault / "graph.html").write_text("<html>Carte</html>", encoding="utf-8")
        (self.vault / "config.env").write_text("DEEPSEEK_API_KEY=cle-secrete-test\n", encoding="utf-8")
        env = mock.patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.mock = mock.patch.object(page_server, "repondre_borne", return_value={
            "reponse": "Réponse fictive.", "sources": []}).start()
        self.addCleanup(mock.patch.stopall)
        self.serveurs = []
        self.addCleanup(self.fermer)
        self.srv = self.ouvrir(local=True)

    def ouvrir(self, **kwargs):
        import threading
        serveur = page_server.ServeurBobine(("127.0.0.1", 0), self.vault, **kwargs)
        thread = threading.Thread(target=serveur.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        self.serveurs.append((serveur, thread))
        return serveur

    def fermer(self):
        for s, t in self.serveurs:
            s.shutdown()
            s.server_close()
            t.join(timeout=2)

    def requete(self, methode="GET", chemin="/api/bobine", corps=None, headers=None, serveur=None):
        import http.client
        import json
        s = serveur or self.srv
        connexion = http.client.HTTPConnection("127.0.0.1", s.server_address[1], timeout=2)
        try:
            connexion.request(methode, chemin, body=corps, headers=headers or {})
            rep = connexion.getresponse()
            texte = rep.read().decode("utf-8")
            try:
                objet = json.loads(texte)
            except ValueError:
                objet = texte
            return rep.status, dict(rep.getheaders()), objet
        finally:
            connexion.close()

    def entetes(self, serveur=None, public=False):
        s = serveur or self.srv
        origine = s.origine_publique if public else "http://127.0.0.1:" + str(s.server_address[1])
        from urllib.parse import urlsplit
        h = {"Content-Type": "application/json", "Origin": origine, "Host": urlsplit(origine).netloc,
             "Sec-Fetch-Site": "same-origin", "X-Bobine-Token": s.jeton}
        if s.mot_de_passe:
            h["Authorization"] = "Basic " + base64.b64encode(("bobine:" + s.mot_de_passe).encode()).decode()
        return h

    def post(self, headers=None, question="organisation", serveur=None, public=False, brut=None):
        import json
        h = self.entetes(serveur, public) if headers is None else headers
        return self.requete("POST", "/api/demander", brut if brut is not None else json.dumps({"question": question}), h, serveur)

    def test_decouverte_et_post_legitime(self):
        statut, h, d = self.requete()
        self.assertEqual(statut, 200)
        self.assertTrue(d["disponible"])
        self.assertEqual(d["jeton"], self.srv.jeton)
        self.assertNotIn("cle-secrete-test", str(d))
        self.assertEqual(h["Cache-Control"], "no-store")
        self.assertEqual(self.post()[0], 200)
        self.mock.assert_called_once_with(self.vault, "organisation", historique=[], fiche=None)

    def test_autre_site_tente_appeler_et_obtenir_jeton(self):
        h = self.entetes()
        h.update(Origin="https://pirate.example", **{"Sec-Fetch-Site": "cross-site"})
        # Même avec le jeton connu, un autre site est refusé.
        self.assertEqual(self.post(headers=h)[0], 403)
        self.assertEqual(self.requete(headers=h)[0], 403)
        status, entetes, _ = self.requete("OPTIONS", "/api/demander", headers={
            "Origin": "https://pirate.example", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Bobine-Token,Content-Type"})
        self.assertEqual(status, 403)
        self.assertFalse(any(n.lower().startswith("access-control-allow") for n in entetes))
        self.mock.assert_not_called()
        self.assertFalse((self.vault / page_server.FICHIER_COMPTEUR).exists())

    def test_origine_nulle_absente_et_jeton_obligatoire(self):
        for champ, valeur in (("Origin", None), ("Origin", "null"), ("X-Bobine-Token", None),
                              ("X-Bobine-Token", "invalide"), ("Sec-Fetch-Site", "same-site"),
                              ("Sec-Fetch-Site", "cross-site")):
            h = self.entetes()
            if valeur is None:
                del h[champ]
            else:
                h[champ] = valeur
            self.assertEqual(self.post(headers=h)[0], 403, (champ, valeur))
        self.mock.assert_not_called()

    def test_ancien_navigateur_sans_sec_fetch_origin_et_jeton_restent_requis(self):
        h = self.entetes()
        del h["Sec-Fetch-Site"]
        self.assertEqual(self.post(headers=h)[0], 200)

    def test_rebinding_et_faux_forwarded_refuses(self):
        h = self.entetes()
        h.update(Host="pirate.example", Origin="http://pirate.example",
                 **{"X-Forwarded-Host": "127.0.0.1", "X-Forwarded-Proto": "http"})
        self.assertEqual(self.post(headers=h)[0], 403)
        self.assertEqual(self.requete(headers=h)[0], 403)
        h = self.entetes()
        h["Origin"] = "http://localhost:" + str(self.srv.server_address[1])
        self.assertEqual(self.post(headers=h)[0], 403)  # deux origines locales distinctes

    def test_formulaire_et_payload_trop_long_refuses_avant_moteur(self):
        for contenu in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
            h = self.entetes()
            h["Content-Type"] = contenu
            self.assertEqual(self.post(headers=h)[0], 415)
        self.assertEqual(self.post(brut="x" * (page_server.MAX_CORPS + 1))[0], 413)
        for brut in ("{", "null", "[]", '{"question":42}', '{"question":"x", "chemin":"/etc/passwd"}'):
            self.assertEqual(self.post(brut=brut)[0], 400)
        self.assertEqual(self.post(question="x" * 2001)[0], 400)
        self.mock.assert_not_called()

    def test_corps_transfert_chunked_et_encodage_refuses(self):
        for champ in ("Transfer-Encoding", "Content-Encoding"):
            h = self.entetes()
            h[champ] = "chunked" if champ == "Transfer-Encoding" else "gzip"
            self.assertEqual(self.post(headers=h)[0], 400)
        self.mock.assert_not_called()

    def test_tunnel_public_exige_auth_origine_et_limite_globale(self):
        s = self.ouvrir(mot_de_passe="secret-page", origine="https://bobine.example")
        self.assertEqual(self.requete(headers={"Host": "bobine.example"}, serveur=s)[0], 401)
        h = self.entetes(s, public=True)
        self.assertEqual(self.requete(headers=h, serveur=s)[0], 200)
        for _ in range(page_server.MAX_PAR_MINUTE):
            self.assertEqual(self.post(serveur=s, public=True)[0], 200)
        # Changer l'IP annoncée ne contourne pas la limite commune à l'installation.
        h["X-Forwarded-For"] = "192.0.2.123"
        self.assertEqual(self.post(headers=h, serveur=s)[0], 429)
        self.assertEqual(self.mock.call_count, page_server.MAX_PAR_MINUTE)
        h["Origin"] = "https://autre.example"
        self.assertEqual(self.post(headers=h, serveur=s)[0], 403)

    def test_adresse_publique_sans_origine_lecture_seule(self):
        s = self.ouvrir(mot_de_passe="p")
        h = {"Host": "bobine.example", "Authorization": "Basic " + base64.b64encode(b":p").decode()}
        self.assertEqual(self.requete(chemin="/vault.html", headers=h, serveur=s)[0], 200)
        self.assertEqual(self.requete(headers=h, serveur=s)[0], 403)

    def test_tunnel_amont_garde_origine_et_jeton(self):
        s = self.ouvrir(amont=True, origine="https://bobine.example")
        self.assertEqual(self.post(serveur=s, public=True)[0], 200)
        h = self.entetes(s, public=True)
        h.pop("X-Bobine-Token")
        self.assertEqual(self.post(headers=h, serveur=s)[0], 403)

    def test_quota_journalier_persistant_apres_redemarrage(self):
        import json
        import time
        chemin = self.vault / page_server.FICHIER_COMPTEUR
        chemin.write_text(json.dumps([time.time() - 120] * page_server.MAX_PAR_JOUR), encoding="utf-8")
        self.assertEqual(self.post()[0], 429)
        s2 = self.ouvrir(local=True)
        self.assertEqual(self.post(serveur=s2)[0], 429)
        self.mock.assert_not_called()

    def test_compteur_abime_ne_remet_pas_le_quota_a_zero(self):
        chemin = self.vault / page_server.FICHIER_COMPTEUR
        chemin.write_text("abîmé", encoding="utf-8")
        self.assertEqual(self.post()[0], 503)
        self.assertEqual(chemin.read_text(encoding="utf-8"), "abîmé")
        self.mock.assert_not_called()

    def test_pas_de_conversation_ecrite_compteur_prive(self):
        import json
        import stat
        self.post(question="QUESTION PRIVEE")
        chemin = self.vault / page_server.FICHIER_COMPTEUR
        d = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(len(d), 1)
        self.assertIsInstance(d[0], (int, float))
        self.assertEqual(stat.S_IMODE(chemin.stat().st_mode), 0o600)
        self.assertEqual(self.requete(chemin="/" + page_server.FICHIER_COMPTEUR)[0], 404)

    def test_deux_questions_simultanees_et_verrou_libere(self):
        import threading
        entree, liberation = threading.Event(), threading.Event()
        def attente(*args, **kwargs):
            entree.set()
            liberation.wait(2)
            return {"reponse": "Réponse", "sources": []}
        self.mock.side_effect = attente
        resultats = []
        t = threading.Thread(target=lambda: resultats.append(self.post()))
        t.start()
        try:
            self.assertTrue(entree.wait(1))
            self.assertEqual(self.post()[0], 409)
            autre = self.ouvrir(local=True)
            self.assertEqual(self.post(serveur=autre)[0], 409)
        finally:
            liberation.set()
            t.join(3)
        self.assertEqual(resultats[0][0], 200)
        self.assertEqual(self.post()[0], 200)

    def test_panne_fournisseur_sans_secret_et_sans_blocage(self):
        self.mock.side_effect = RuntimeError("cle-secrete-test")
        status, _, d = self.post()
        self.assertEqual(status, 503)
        self.assertNotIn("cle-secrete-test", str(d))
        self.mock.side_effect = page_server.demander.ErreurDemande("Réessaie plus tard.", "delai_depasse")
        self.assertEqual(self.post()[0], 504)
        self.mock.side_effect = None
        self.assertEqual(self.post()[0], 200)

    def test_fichiers_secrets_et_profil_non_editable(self):
        for nom in ("config.env", "raw/a.md", "Mon%20profil.txt", "index.md", "../config.env", ".bobine-jeton"):
            self.assertEqual(self.requete(chemin="/" + nom)[0], 404)
        self.assertEqual(self.requete("POST", "/api/profil", "{}", self.entetes())[0], 404)
        (self.vault / "vault.html").unlink()
        (self.vault / "vault.html").symlink_to(self.vault / "config.env")
        self.assertEqual(self.requete(chemin="/vault.html")[0], 404)

    def test_sans_cle_aucun_jeton_actif(self):
        (self.vault / "config.env").unlink()
        self.assertEqual(self.requete()[2], {"disponible": False, "jeton": ""})
        self.assertEqual(self.post()[0], 503)
        self.mock.assert_not_called()

    def test_mac_refuse_toute_ecoute_reseau(self):
        for adresse in ("0.0.0.0", "::", "localhost", "192.0.2.1"):
            with self.assertRaises(ValueError):
                page_server.ServeurBobine((adresse, 0), self.vault, local=True)
        with self.assertRaises(ValueError):
            page_server.ServeurBobine(("127.0.0.1", 0), self.vault, local=True, origine="https://bobine.example")
        with self.assertRaises(ValueError):
            page_server.ServeurBobine(("127.0.0.1", 0), self.vault)

    def test_origines_configurees_strictes(self):
        for valeur in ("null", "https://bobine.example/a", "https://u:p@bobine.example", "https://bobine.example#x",
                       "https://bobine.example?x=y", "https://bobine.example\n", "http://bobine.example:99999"):
            self.assertIsNone(page_server.origine_valide(valeur), valeur)
        self.assertEqual(page_server.origine_valide("https://bobine.example:443"), "https://bobine.example")

    def test_parite_du_nouveau_coeur(self):
        racine = Path(__file__).resolve().parents[1]
        if racine.name == "linux":
            racine = racine.parent
        # Dans un vault installé sans dépôt, ce garde-fou n'est pas applicable.
        if not (racine / "linux").is_dir():
            self.skipTest("Pas de dépôt complet")
        for fichier in ("page_server.py", "demander.py", "tests/test_demander.py", "tests/test_page_server.py"):
            self.assertEqual((racine / fichier).read_bytes(), (racine / "linux" / fichier).read_bytes(), fichier)


    def test_requetes_intersites_nepuisent_pas_admission_legitime(self):
        for _ in range(125):
            h = self.entetes()
            h["Origin"] = "https://pirate.example"
            self.assertEqual(self.post(headers=h)[0], 403)
        self.assertEqual(self.requete()[0], 200)
        self.assertEqual(self.post()[0], 200)

    def test_non_authentifie_nepuise_pas_admission_publique(self):
        s = self.ouvrir(mot_de_passe="secret", origine="https://bobine.example")
        for _ in range(125):
            self.assertEqual(self.requete(serveur=s, headers={"Host": "bobine.example"})[0], 401)
        self.assertEqual(self.post(serveur=s, public=True)[0], 200)

    def test_echeance_absolue_entetes_et_corps_lents(self):
        import socket
        import time
        from unittest import mock
        with mock.patch.object(page_server, "DELAI_ENTREE", 0.15):
            for corps in (False, True):
                client = socket.create_connection(self.srv.server_address, timeout=1)
                try:
                    if corps:
                        h = self.entetes()
                        texte = "POST /api/demander HTTP/1.1\r\n" + "".join(k + ": " + v + "\r\n" for k, v in h.items())
                        client.sendall((texte + "Content-Length: 2000\r\n\r\n").encode())
                    else:
                        client.sendall(b"GET / HTTP/1.1\r\nX-Lent: ")
                    debut = time.monotonic()
                    while time.monotonic() - debut < 0.3:
                        try:
                            client.sendall(b"x")
                        except OSError:
                            break
                        time.sleep(0.025)
                    self.assertFalse(self.srv.occupe.locked())
                    # Le serveur a libéré sa connexion, malgré les octets réguliers.
                    self.assertEqual(self.srv.connexions._value, page_server.MAX_CONNEXIONS)
                finally:
                    client.close()
        self.mock.assert_not_called()
        self.assertEqual(self.post()[0], 200)

    def test_entetes_dupliques_refuses(self):
        import http.client
        for nom, valeur in (("Host", "pirate.example"), ("Origin", "https://pirate.example"),
                            ("X-Bobine-Token", self.srv.jeton), ("Content-Length", "25")):
            c = http.client.HTTPConnection(*self.srv.server_address, timeout=1)
            try:
                c.putrequest("POST", "/api/demander", skip_host=True)
                for k, v in self.entetes().items():
                    c.putheader(k, v)
                c.putheader("Content-Length", "25")
                c.putheader(nom, valeur)
                c.endheaders(b'{"question":"organisation"}')
                r = c.getresponse()
                self.assertIn(r.status, (403, 411))
                r.read()
            finally:
                c.close()
        self.mock.assert_not_called()

    def test_compteur_verrou_interprocessus(self):
        import fcntl
        import os
        verrou = (self.vault / page_server.FICHIER_COMPTEUR).with_suffix(".lock")
        fd = os.open(verrou, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            with self.assertRaises(BlockingIOError):
                page_server.Compteur(self.vault).reserver()
        finally:
            os.close(fd)
        self.assertIsNone(page_server.Compteur(self.vault).reserver())


class MoteurIsole(unittest.TestCase):
    def test_sous_processus_sans_fournisseur_si_aucune_fiche(self):
        from unittest import mock
        import os
        with tempfile.TemporaryDirectory() as dossier, mock.patch.dict(os.environ, {}, clear=True):
            r = page_server.repondre_borne(Path(dossier), "une question absente")
            self.assertEqual(r["sources"], [])
            self.assertEqual(r["reponse"], page_server.demander.SANS_RESULTAT)

    def test_delai_global_arrete_et_recolte_le_processus(self):
        import subprocess
        import time
        from unittest import mock
        vrai_popen = subprocess.Popen
        enfants = []
        def lent(*args, **kwargs):
            # Simule un DNS, une poignée TLS ou des en-têtes sans fin.
            self.assertNotIn("cle-secrete", str(args))
            enfant = vrai_popen([sys.executable, "-c", "import time; time.sleep(5)"], **kwargs)
            enfants.append(enfant)
            return enfant
        with tempfile.TemporaryDirectory() as dossier, mock.patch.object(page_server.subprocess, "Popen", side_effect=lent), \
                mock.patch.object(page_server, "DELAI_DEMANDE", 0.2):
            avant = time.monotonic()
            with self.assertRaises(page_server.demander.ErreurDemande) as e:
                page_server.repondre_borne(Path(dossier), "question privée")
            self.assertEqual(e.exception.code, "delai_depasse")
            self.assertLess(time.monotonic() - avant, 2)
            self.assertIsNotNone(enfants[0].poll())

    def test_isolation_vers_faux_fournisseur_http_reel(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        demandes = []
        class FauxFournisseur(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                demandes.append(d)
                identifiant = json.loads(d["messages"][1]["content"])["fiches"][0]["id"]
                resultat = json.dumps({"reponse": "Le vélo utilise une chambre à air.", "sources": [identifiant]})
                corps = json.dumps({"choices": [{"message": {"content": resultat}, "finish_reason": "stop"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)
        serveur = ThreadingHTTPServer(("127.0.0.1", 0), FauxFournisseur)
        t = threading.Thread(target=serveur.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        t.start()
        try:
            with tempfile.TemporaryDirectory() as dossier:
                r = Path(dossier)
                (r / "raw").mkdir()
                (r / "raw/yt_velo00001.md").write_text("---\nsource: https://youtu.be/velo00001\n---\n# Le vélo\n## Transcription\nLe vélo utilise une chambre à air.", encoding="utf-8")
                (r / "index.md").write_text("### Le vélo\n- lien : https://youtu.be/velo00001\n- auteur : Test\n- thèmes : vélo\n- contenu : Réparer son vélo.\n", encoding="utf-8")
                (r / "config.env").write_text("API_KEY=faux-service-local\nAPI_MODEL=demo\nAPI_BASE_URL=http://127.0.0.1:" + str(serveur.server_port), encoding="utf-8")
                resultat = page_server.repondre_borne(r, "Comment réparer mon vélo ?")
                self.assertEqual(len(demandes), 1)
                self.assertEqual(resultat["sources"][0]["ancre"], "#f-yt_velo00001")
                self.assertNotIn("faux-service-local", str(resultat))
        finally:
            serveur.shutdown()
            serveur.server_close()
            t.join(1)


if __name__ == "__main__":
    unittest.main()
