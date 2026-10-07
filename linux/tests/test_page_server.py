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


if __name__ == "__main__":
    unittest.main()
