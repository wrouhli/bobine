#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests de inbox_server.py — extraction des liens et ajout à la boîte.

Lancement (aucune dépendance à installer) :

    python3 -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inbox_server  # noqa: E402


class LiensDuCorps(unittest.TestCase):
    """liens_du_corps : extraction + dédoublonnage des liens reconnus."""

    def test_extrait_et_dedoublonne(self):
        corps = ("regarde https://www.instagram.com/reel/AAA111/ puis "
                 "https://youtu.be/BBB222?t=1 et encore "
                 "https://www.instagram.com/reel/AAA111/ !")
        self.assertEqual(
            inbox_server.liens_du_corps(corps),
            ["https://www.instagram.com/reel/AAA111/",
             "https://youtu.be/BBB222?t=1"])

    def test_aucun_lien(self):
        self.assertEqual(inbox_server.liens_du_corps("bonjour, rien ici"), [])

    def test_supprime_ponctuation_finale(self):
        self.assertEqual(
            inbox_server.liens_du_corps("vois https://youtu.be/BBB222."),
            ["https://youtu.be/BBB222"])


class AjoutBoite(unittest.TestCase):
    """ajouter_a_la_boite : ajout seul, création des dossiers manquants."""

    def test_ajoute_en_ajout_seul(self):
        with tempfile.TemporaryDirectory() as dossier:
            boite = Path(dossier) / "sous" / "inbox.txt"
            nombre = inbox_server.ajouter_a_la_boite(boite, ["https://youtu.be/BBB222?t=1"])
            self.assertEqual(nombre, 1)
            inbox_server.ajouter_a_la_boite(boite, ["https://www.instagram.com/reel/AAA111/"])
            self.assertEqual(
                boite.read_text(encoding="utf-8"),
                "https://youtu.be/BBB222?t=1\nhttps://www.instagram.com/reel/AAA111/\n")

    def test_rien_a_ajouter(self):
        with tempfile.TemporaryDirectory() as dossier:
            boite = Path(dossier) / "inbox.txt"
            self.assertEqual(inbox_server.ajouter_a_la_boite(boite, []), 0)
            self.assertFalse(boite.exists())


class JetonDeConfig(unittest.TestCase):
    """jeton_de_config : lecture de INBOX_TOKEN dans config.env."""

    def test_lit_le_jeton(self):
        with tempfile.TemporaryDirectory() as dossier:
            (Path(dossier) / "config.env").write_text(
                '# commentaire\nNOM="Mon Bobine"\nINBOX_TOKEN="abc123"\n',
                encoding="utf-8")
            jeton = inbox_server.jeton_de_config(Path(dossier), Path(dossier))
        self.assertEqual(jeton, "abc123")

    def test_absent(self):
        with tempfile.TemporaryDirectory() as dossier:
            self.assertEqual(inbox_server.jeton_de_config(Path(dossier), Path(dossier)), "")


class CorpsJson(unittest.TestCase):
    """liens_du_corps : tolère un corps JSON (les Raccourcis iOS en envoient)."""

    def test_json_slashes_echappes(self):
        corps = '{"text":"https:\\/\\/www.instagram.com\\/reel\\/DeM2rcXDP6M\\/"}'
        self.assertEqual(inbox_server.liens_du_corps(corps),
                         ["https://www.instagram.com/reel/DeM2rcXDP6M/"])

    def test_json_liste_imbriquee(self):
        corps = '["https://youtu.be/BBB222?t=1", {"url": "https://youtu.be/CCC333"}]'
        self.assertEqual(inbox_server.liens_du_corps(corps),
                         ["https://youtu.be/BBB222?t=1", "https://youtu.be/CCC333"])

    def test_json_invalide_retombe_sur_le_brut(self):
        corps = '{ "text": https://youtu.be/BBB222 '
        self.assertEqual(inbox_server.liens_du_corps(corps), ["https://youtu.be/BBB222"])


if __name__ == "__main__":
    unittest.main()
