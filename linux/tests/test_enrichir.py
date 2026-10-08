#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests de enrichir.py — identifiants Instagram, lecture de config, mode sans clé.

Lancement (aucune dépendance à installer) :

    python3 -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class IndexEnAttente(unittest.TestCase):
    """Mode sans clé : entrées « résumé en attente » et rattrapage."""

    def _vault_avec_une_fiche(self, dossier):
        racine = Path(dossier)
        (racine / "raw").mkdir()
        (racine / "raw" / "yt_abc.md").write_text(
            "---\nsource: https://youtu.be/abc\nauteur: Testeur\n"
            "traite_le: 2026-01-01\nstatut: brut\n---\n\n"
            "# Une vidéo de test\n\n## Transcription\nBonjour.\n",
            encoding="utf-8")
        return racine

    def _sans_cle(self, racine, *extra):
        argv = ["enrichir.py", "--vault", str(racine)] + list(extra)
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict(os.environ, {}, clear=True):
            return enrichir.main()

    def test_fonctionne_sans_cle_et_ajoute_une_entree_en_attente(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault_avec_une_fiche(dossier)
            self.assertEqual(self._sans_cle(racine, "--no-pages"), 0)
            texte = (racine / "index.md").read_text(encoding="utf-8")
        self.assertIn("### Une vidéo de test", texte)
        self.assertIn("https://youtu.be/abc", texte)
        self.assertIn(enrichir.MARQUEUR_ATTENTE, texte)

    def test_pas_de_doublon_au_deuxieme_passage(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault_avec_une_fiche(dossier)
            self._sans_cle(racine, "--no-pages")
            self._sans_cle(racine, "--no-pages")
            texte = (racine / "index.md").read_text(encoding="utf-8")
        self.assertEqual(texte.count("### Une vidéo de test"), 1)
        self.assertEqual(texte.count("https://youtu.be/abc"), 1)

    def test_liens_deja_indexes_ignore_les_entrees_en_attente(self):
        with tempfile.TemporaryDirectory() as dossier:
            index = Path(dossier) / "index.md"
            index.write_text(
                "# Index du Vault\n\n"
                "### Déjà résumée\n- lien : https://youtu.be/x\n- auteur : a\n"
                "- thèmes : ia\n- contenu : c\n\n"
                "### En attente\n- lien : https://youtu.be/y\n- auteur : b\n"
                "- thèmes : " + enrichir.THEMES_ATTENTE + "\n"
                "- contenu : " + enrichir.CONTENU_ATTENTE + "\n",
                encoding="utf-8")
            _, urls = enrichir.liens_deja_indexes(index)
        self.assertIn("https://youtu.be/x", urls)
        self.assertNotIn("https://youtu.be/y", urls)

    def test_remplace_une_entree_en_attente(self):
        with tempfile.TemporaryDirectory() as dossier:
            index = Path(dossier) / "index.md"
            index.write_text(
                "# Index du Vault\n\n"
                "### En attente\n- lien : https://youtu.be/y\n- auteur : b\n"
                "- thèmes : " + enrichir.THEMES_ATTENTE + "\n"
                "- contenu : " + enrichir.CONTENU_ATTENTE + "\n",
                encoding="utf-8")
            entree = ("### Vraie fiche\n- lien : https://youtu.be/y\n"
                      "- auteur : b\n- thèmes : ia\n- contenu : Un vrai résumé.\n")
            self.assertTrue(
                enrichir.remplacer_entree_en_attente(index, "https://youtu.be/y", entree))
            texte = index.read_text(encoding="utf-8")
        self.assertNotIn(enrichir.MARQUEUR_ATTENTE, texte)
        self.assertIn("### Vraie fiche", texte)
        self.assertEqual(texte.count("https://youtu.be/y"), 1)
        self.assertTrue(texte.startswith("# Index du Vault"))

    def test_rien_a_remplacer(self):
        with tempfile.TemporaryDirectory() as dossier:
            index = Path(dossier) / "index.md"
            avant = ("# Index du Vault\n\n### Déjà résumée\n"
                     "- lien : https://youtu.be/x\n- auteur : a\n"
                     "- thèmes : ia\n- contenu : c\n")
            index.write_text(avant, encoding="utf-8")
            entree = ("### Vraie fiche\n- lien : https://youtu.be/x\n"
                      "- auteur : a\n- thèmes : ia\n- contenu : r\n")
            self.assertFalse(
                enrichir.remplacer_entree_en_attente(index, "https://youtu.be/x", entree))
            self.assertEqual(index.read_text(encoding="utf-8"), avant)


class TitreProvisoire(unittest.TestCase):
    """titre_provisoire : premier « # … » de la fiche, sinon le nom du fichier."""

    def test_premier_titre(self):
        texte = "---\nsource: x\n---\n\n# Un bon titre\nsuite"
        self.assertEqual(enrichir.titre_provisoire(Path("fiche.md"), texte), "Un bon titre")

    def test_repli_sur_le_nom_de_fichier(self):
        self.assertEqual(
            enrichir.titre_provisoire(Path("/tmp/yt_abc.md"), "pas de titre"), "yt_abc")


if __name__ == "__main__":
    unittest.main()
