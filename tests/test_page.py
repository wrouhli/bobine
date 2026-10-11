#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests de generate_page.py (et graphe.py) — liens sûrs, repères, lecture de l'index.

Lancement (aucune dépendance à installer) :

    python3 -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate_page  # noqa: E402
import graphe  # noqa: E402


class LienSur(unittest.TestCase):
    """lien_sur : seuls les liens web deviennent cliquables."""

    def test_liens_web_gardes(self):
        for lien in ("https://www.instagram.com/reel/A/", "http://youtu.be/abcdef"):
            self.assertEqual(generate_page.lien_sur(lien), lien)

    def test_autres_schemas_refuses(self):
        for lien in ("javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,x",
                     "file:///etc/passwd", "vbscript:x", "", None,
                     'https://x" onmouseover="alert(1)'):
            self.assertEqual(generate_page.lien_sur(lien), "")


class Remplir(unittest.TestCase):
    """remplir : un seul passage, le texte inséré n'est jamais relu."""

    def test_valeur_contenant_un_repere(self):
        modele = "<h1>__TITRE__</h1><p>__CHIPS__</p>"
        page = generate_page.remplir(modele, {"__TITRE__": "Titre __CHIPS__",
                                              "__CHIPS__": "<b>ia</b>"})
        self.assertEqual(page, "<h1>Titre __CHIPS__</h1><p><b>ia</b></p>")

    def test_reperes_imbriques(self):
        page = generate_page.remplir("__STATS__ / __STATS_G__",
                                     {"__STATS__": "1", "__STATS_G__": "2"})
        self.assertEqual(page, "1 / 2")


class LireIndex(unittest.TestCase):
    """lire_index : la première ligne de chaque champ fait foi."""

    def test_premier_lien_garde(self):
        with tempfile.TemporaryDirectory() as dossier:
            index = Path(dossier) / "index.md"
            index.write_text(
                "# Index\n\n### Une fiche\n- lien : https://www.instagram.com/reel/A/\n"
                "- auteur : a\n- thèmes : ia\n- contenu : c\n"
                "- lien : javascript:alert(1)\n", encoding="utf-8")
            entrees = generate_page.lire_index(index)
        self.assertEqual(entrees[0]["lien"], "https://www.instagram.com/reel/A/")

    def test_dates_youtube_distinctes(self):
        a = generate_page.normaliser_lien("https://www.youtube.com/watch?v=AAAAAAA&si=1")
        b = generate_page.normaliser_lien("https://www.youtube.com/watch?v=BBBBBBB")
        self.assertNotEqual(a, b)
        self.assertEqual(a, generate_page.normaliser_lien("https://youtu.be/AAAAAAA?si=2"))


class PageComplete(unittest.TestCase):
    """main() : une page générée à partir d'un index piégé reste saine."""

    def test_index_piege(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            (racine / "config.env").write_text("CARTE=non\nSYNC_ICLOUD=non\n", encoding="utf-8")
            (racine / "index.md").write_text(
                "# Index\n\n"
                "### Astuces __CHIPS__ et __STATS__\n"
                "- lien : javascript:alert(document.domain)\n- auteur : a\n"
                "- thèmes : ia\n- contenu : c\n\n"
                "### Vraie fiche\n- lien : https://www.instagram.com/reel/A/\n"
                "- auteur : b\n- thèmes : ia\n- contenu : d\n", encoding="utf-8")
            argv = ["generate_page.py", "--vault", str(racine)]
            with mock.patch.object(sys, "argv", argv):
                generate_page.main()
            page = (racine / "vault.html").read_text(encoding="utf-8")
        self.assertNotIn("javascript:", page)
        self.assertEqual(page.count('class="carte"'), 2)
        self.assertIn("Astuces __CHIPS__ et __STATS__", page)
        self.assertIn('href="https://www.instagram.com/reel/A/"', page)


class Graphe(unittest.TestCase):
    """graphe.py retrouve les fiches YouTube (même nom de fichier que l'ingestion)."""

    def test_identifiant_youtube(self):
        self.assertEqual(graphe.identifiant("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
                         "yt_dQw4w9WgXcQ")


if __name__ == "__main__":
    unittest.main()
