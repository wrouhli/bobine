#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests de ingest.py — nettoyage SRT, identifiants, noms de fichiers.

Lancement (aucune dépendance à installer) :

    python3 -m unittest discover -s tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ingest  # noqa: E402


class NettoyageSrt(unittest.TestCase):
    """nettoyer_srt : SRT/VTT → texte brut."""

    def test_srt_simple(self):
        texte = ("1\n"
                 "00:00:01,000 --> 00:00:03,000\n"
                 "Bonjour tout le monde\n"
                 "\n"
                 "2\n"
                 "00:00:03,500 --> 00:00:05,000\n"
                 "ça va bien")
        self.assertEqual(ingest.nettoyer_srt(texte),
                         "Bonjour tout le monde ça va bien")

    def test_cues_roulants_sont_fusionnes(self):
        # Les sous-titres automatiques répètent la fin du cue précédent.
        texte = ("1\n"
                 "00:00:01,000 --> 00:00:02,000\n"
                 "la recette de la tarte\n"
                 "\n"
                 "2\n"
                 "00:00:02,000 --> 00:00:03,000\n"
                 "la recette de la tarte tatin est simple")
        self.assertEqual(ingest.nettoyer_srt(texte),
                         "la recette de la tarte tatin est simple")

    def test_entetes_vtt_ignores(self):
        texte = ("WEBVTT\nKind: captions\nLanguage: fr\n"
                 "\n"
                 "00:00:01.000 --> 00:00:02.000\n"
                 "Bonjour")
        self.assertEqual(ingest.nettoyer_srt(texte), "Bonjour")

    def test_balises_retirees(self):
        texte = ("1\n"
                 "00:00:01,000 --> 00:00:02,000\n"
                 "<c>couleur</c> et <b>gras</b>")
        self.assertEqual(ingest.nettoyer_srt(texte), "couleur et gras")

    def test_texte_vide(self):
        self.assertEqual(ingest.nettoyer_srt(""), "")


class Identifiants(unittest.TestCase):
    """identifiant : extraction de l'identifiant + nom de fichier sûr."""

    def test_youtube_watch(self):
        self.assertEqual(
            ingest.identifiant("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "yt_dQw4w9WgXcQ")

    def test_youtube_youtu_be(self):
        self.assertEqual(
            ingest.identifiant("https://youtu.be/dQw4w9WgXcQ"),
            "yt_dQw4w9WgXcQ")

    def test_youtube_shorts_et_query(self):
        self.assertEqual(
            ingest.identifiant("https://www.youtube.com/shorts/AbCdEf12345"),
            "yt_AbCdEf12345")
        self.assertEqual(
            ingest.identifiant("https://m.youtube.com/watch?v=ABC123xy&t=10s"),
            "yt_ABC123xy")

    def test_instagram_reel_avec_query(self):
        # Un lien partagé par l'appli a un « / » juste avant le « ? ».
        self.assertEqual(
            ingest.identifiant("https://www.instagram.com/reel/C1a2B3c4D5e/?stkn=abc"),
            "insta_C1a2B3c4D5e")

    def test_tiktok_video(self):
        self.assertEqual(
            ingest.identifiant("https://www.tiktok.com/@chef/video/7123456789012"),
            "tiktok_7123456789012")

    def test_nom_jamais_dangereux(self):
        # Un nom de fichier ne doit contenir que [A-Za-z0-9_-] : jamais de
        # « / », de « .. », d'espaces, de « % », de caractères de contrôle…
        for lien in ("https://www.tiktok.com/@u/..%2F..%2Fetc/passwd",
                     "https://www.instagram.com/reel/ab/../cd;rm -rf",
                     "https://www.tiktok.com/@u/vidéo/abc\x00def"):
            nom = ingest.identifiant(lien)
            self.assertRegex(nom, r"^(yt|insta|tiktok)_[A-Za-z0-9_-]+$", lien)
            self.assertNotIn("..", nom)
            self.assertNotIn("/", nom)
            self.assertNotIn(" ", nom)

    def test_troncature_a_40_caracteres(self):
        lien = "https://www.tiktok.com/@u/video/" + "A" * 60
        self.assertEqual(ingest.identifiant(lien), "tiktok_" + "A" * 40)

    def test_repli_quand_segment_inutilisable(self):
        # Dernier segment entièrement nettoyé → repli sur un court chiffre.
        nom = ingest.identifiant("https://www.tiktok.com/@u/video/...")
        self.assertRegex(nom, r"^tiktok_\d+$")


class ExtraireLiens(unittest.TestCase):
    """extraire_liens : filtre les domaines, dédoublonne, nettoie la ponctuation."""

    def test_filtre_dedoublonne_et_nettoie(self):
        contenu = ("regarde https://www.instagram.com/reel/AAA111/, puis "
                   "https://youtu.be/BBB222?t=1 et encore "
                   "https://www.instagram.com/reel/AAA111/ !\n"
                   "https://example.com/pas-pris")
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "liens.txt"
            fichier.write_text(contenu, encoding="utf-8")
            liens = ingest.extraire_liens(fichier)
        self.assertEqual(liens, ["https://www.instagram.com/reel/AAA111/",
                                 "https://youtu.be/BBB222?t=1"])


if __name__ == "__main__":
    unittest.main()
