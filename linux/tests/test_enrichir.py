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


class Pluriel(unittest.TestCase):
    """pluriel : singulier pour 0 et 1, pluriel à partir de 2."""

    def test_singulier_pour_zero_et_un(self):
        self.assertEqual(enrichir.pluriel(0, "échec"), "0 échec")
        self.assertEqual(enrichir.pluriel(1, "fiche"), "1 fiche")
        self.assertEqual(enrichir.pluriel(1, "réussite"), "1 réussite")

    def test_pluriel_a_partir_de_deux(self):
        self.assertEqual(enrichir.pluriel(2, "fiche"), "2 fiches")
        self.assertEqual(enrichir.pluriel(3, "lien"), "3 liens")
        self.assertEqual(enrichir.pluriel(12, "thème"), "12 thèmes")


if __name__ == "__main__":
    unittest.main()


class EntreeSurUneLigne(unittest.TestCase):
    """construire_entree : une réponse du modèle ne peut pas fabriquer de lignes."""

    def test_retours_a_la_ligne_neutralises(self):
        entree = enrichir.construire_entree(
            "Titre\n### Fausse entrée", "https://youtu.be/x", "a",
            ["ia\n- lien : javascript:alert(1)", "seo, ads"],
            "Normal.\n- lien : javascript:alert(1)\n### Fausse")
        lignes = entree.splitlines()
        self.assertEqual(len(lignes), 5)
        self.assertEqual(sum(1 for l in lignes if l.startswith("- lien :")), 1)
        self.assertEqual(sum(1 for l in lignes if l.startswith("### ")), 1)
        self.assertIn("- lien : https://youtu.be/x", lignes)


class TexteEtLangue(unittest.TestCase):
    """Texte envoyé au modèle et langue des résumés."""

    def test_texte_court_intact(self):
        self.assertEqual(enrichir.texte_pour_le_modele("abc"), "abc")

    def test_texte_long_garde_debut_et_fin(self):
        texte = "D" * 7000 + "M" * 5000 + "F" * 3000
        envoye = enrichir.texte_pour_le_modele(texte)
        self.assertLessEqual(len(envoye), enrichir.TAILLE_MAX_TEXTE + 20)
        self.assertTrue(envoye.startswith("D"))
        self.assertTrue(envoye.endswith("F" * 2000))

    def test_langue(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(enrichir.langue_resumes({}), "fr")
            self.assertEqual(enrichir.langue_resumes({"LANGUE_RESUMES": "EN"}), "en")
            self.assertEqual(enrichir.langue_resumes({"LANGUE_RESUMES": "klingon"}), "fr")

    def test_message_erreur_modele_retire(self):
        import io
        import urllib.error
        erreur = urllib.error.HTTPError(
            "https://api.deepseek.com/v1/chat/completions", 400, "Bad Request", {},
            io.BytesIO(b'{"error":{"message":"Model Not Exist"}}'))
        texte = enrichir.message_erreur(erreur, "deepseek-chat")
        self.assertIn("Model Not Exist", texte)
        self.assertIn("API_MODEL", texte)


class AvecCle(unittest.TestCase):
    """Avec une clé : échecs du service, rattrapage, doublons."""

    def _vault(self, dossier, fiches):
        racine = Path(dossier)
        (racine / "raw").mkdir()
        for nom, source in fiches:
            (racine / "raw" / nom).write_text(
                "---\nsource: " + source + "\nauteur: Testeur\n"
                "traite_le: 2026-01-01\n---\n\n# Vidéo " + nom + "\n\nBonjour.\n",
                encoding="utf-8")
        return racine

    def _lancer(self, racine, reponse):
        argv = ["enrichir.py", "--vault", str(racine), "--no-pages"]
        appels = []

        def faux_resume(*args, **kwargs):
            appels.append(args)
            return reponse
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "cle-de-test"}, clear=True), \
             mock.patch.object(enrichir, "demander_resume", faux_resume):
            code = enrichir.main()
        return code, appels

    def test_echec_du_service_garde_la_fiche_visible(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault(dossier, [("insta_A.md", "https://www.instagram.com/reel/A/")])
            code, _ = self._lancer(racine, None)
            texte = (racine / "index.md").read_text(encoding="utf-8")
            self.assertEqual(code, enrichir.CODE_ECHEC_API)
            self.assertIn("### Vidéo insta_A.md", texte)
            self.assertIn(enrichir.MARQUEUR_ATTENTE, texte)
            # deuxième échec : pas de doublon
            self._lancer(racine, None)
            texte = (racine / "index.md").read_text(encoding="utf-8")
            self.assertEqual(texte.count("https://www.instagram.com/reel/A/"), 1)
            # le service revient : l'entrée en attente est remplacée
            code, _ = self._lancer(racine, {"titre": "Vrai titre", "themes": ["ia"],
                                            "contenu": "Résumé."})
            texte = (racine / "index.md").read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertNotIn(enrichir.MARQUEUR_ATTENTE, texte)
        self.assertIn("### Vrai titre", texte)
        self.assertEqual(texte.count("https://www.instagram.com/reel/A/"), 1)

    def test_pause_apres_plusieurs_echecs_d_affilee(self):
        with tempfile.TemporaryDirectory() as dossier:
            fiches = [("insta_%d.md" % i, "https://www.instagram.com/reel/R%d/" % i)
                      for i in range(6)]
            racine = self._vault(dossier, fiches)
            _, appels = self._lancer(racine, None)
        self.assertEqual(len(appels), enrichir.ECHECS_AVANT_PAUSE)

    def test_meme_video_youtube_partagee_deux_fois(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault(dossier, [
                ("yt_dQw4w9WgXcQ.md", "https://youtu.be/dQw4w9WgXcQ?si=NOUVEAU")])
            (racine / "index.md").write_text(
                "# Index du Vault\n\n### Déjà résumée\n"
                "- lien : https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=ANCIEN\n"
                "- auteur : a\n- thèmes : ia\n- contenu : c\n", encoding="utf-8")
            _, appels = self._lancer(racine, {"titre": "x", "themes": [], "contenu": "y"})
            texte = (racine / "index.md").read_text(encoding="utf-8")
        self.assertEqual(appels, [])
        self.assertEqual(texte.count("dQw4w9WgXcQ"), 1)

    def test_reponse_piegee_ne_cree_pas_de_lien(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault(dossier, [("insta_B.md", "https://www.instagram.com/reel/B/")])
            self._lancer(racine, {"titre": "T", "themes": ["ia"],
                                  "contenu": "ok\n- lien : javascript:alert(1)\n### Faux"})
            texte = (racine / "index.md").read_text(encoding="utf-8")
        lignes = texte.splitlines()
        self.assertEqual(sum(1 for l in lignes if l.startswith("- lien :")), 1)
        self.assertNotIn("\n- lien : javascript", texte)
        self.assertEqual(sum(1 for l in lignes if l.startswith("### ")), 1)
