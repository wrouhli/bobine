#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests de enrichir.py — identifiants Instagram, lecture de config.

Lancement (aucune dépendance à installer) :

    python3 -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import enrichir  # noqa: E402


class CodeCourt(unittest.TestCase):
    """code_court : identifiant d'un lien Instagram (reel, reels, p, tv)."""

    def test_reel(self):
        self.assertEqual(
            enrichir.code_court("https://www.instagram.com/reel/Cxyz123AbC/"),
            "Cxyz123AbC")

    def test_reels_p_tv(self):
        for chemin, attendu in (("reels/AAbbCC", "AAbbCC"),
                                ("p/AbC123", "AbC123"),
                                ("tv/XyZ789", "XyZ789")):
            url = "https://www.instagram.com/" + chemin + "/?igsh=x"
            self.assertEqual(enrichir.code_court(url), attendu)

    def test_autres_liens_ou_vides(self):
        for url in ("https://www.youtube.com/watch?v=abc",
                    "https://www.tiktok.com/@u/video/1",
                    "", None):
            self.assertIsNone(enrichir.code_court(url))


class ChargerConfig(unittest.TestCase):
    """charger_config : lecture clé=valeur des config.env."""

    def test_lit_valeurs_et_ignore_commentaires(self):
        with tempfile.TemporaryDirectory() as dossier:
            (Path(dossier) / "config.env").write_text(
                '# un commentaire\nNOM="Mon Bobine"\nVIDE=\nDEEPSEEK_API_KEY=abc\n',
                encoding="utf-8")
            cfg = enrichir.charger_config(Path(dossier))
        self.assertEqual(cfg.get("NOM"), "Mon Bobine")
        self.assertEqual(cfg.get("DEEPSEEK_API_KEY"), "abc")
        self.assertNotIn("VIDE", cfg)


if __name__ == "__main__":
    unittest.main()
