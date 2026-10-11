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
            appels.append((args, kwargs))
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
        # Aucun nouveau résumé (le seul appel autorisé est le rattrapage du mémo).
        self.assertEqual([a for a in appels if a[1].get("mode") != "memo"], [])
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


def memo_modele(idee="L'idée centrale.", pour_toi=""):
    """Une réponse complète du modèle (résumé + mémo)."""
    reponse = {"titre": "Titre", "themes": ["ia"], "contenu": "Résumé.",
               "a_retenir": ["Point un.", "Point deux."],
               "memo": {"idee": idee, "points": ["Clé 1.", "Clé 2."], "etapes": [], "outils": ["Outil X"]}}
    if pour_toi:
        reponse["pour_toi"] = pour_toi
    return reponse


class Consignes(unittest.TestCase):
    """consigne() : le bon contenu selon l'usage et la présence d'un profil."""

    def test_complet_avec_et_sans_profil(self):
        avec = enrichir.consigne("fr", "complet", True)
        sans = enrichir.consigne("fr", "complet", False)
        for c in (avec, sans):
            self.assertIn('"memo"', c)
            self.assertIn('"a_retenir"', c)
            self.assertIn("N'invente rien", c)
        self.assertIn('"pour_toi"', avec)
        self.assertNotIn('"pour_toi"', sans)

    def test_memo_et_pour_toi_seuls(self):
        memo = enrichir.consigne("fr", "memo", False)
        self.assertNotIn('"titre"', memo)
        self.assertIn('"memo"', memo)
        pour_toi = enrichir.consigne("fr", "pour_toi", True)
        self.assertIn('"pour_toi"', pour_toi)
        self.assertNotIn('"memo"', pour_toi)

    def test_anglais(self):
        self.assertIn("in English", enrichir.consigne("en", "complet", False))

    def test_message_avec_profil_delimite(self):
        avec = enrichir.message_modele("Texte de la fiche.", "fr", "Je forme des gens.")
        self.assertIn("<<<\nJe forme des gens.\n>>>", avec)
        self.assertIn("Texte de la fiche.", avec)
        self.assertNotIn("<<<", enrichir.message_modele("Texte.", "fr", ""))


class MemoPropre(unittest.TestCase):
    """nettoyer_memo : une réponse inutilisable est refusée, le reste est assaini."""

    def test_valide(self):
        memo = enrichir.nettoyer_memo(memo_modele(pour_toi="Pour toi."), True)
        self.assertEqual(memo["memo"]["idee"], "L'idée centrale.")
        self.assertEqual(memo["a_retenir"], ["Point un.", "Point deux."])
        self.assertEqual(memo["pour_toi"], "Pour toi.")

    def test_refuse_sans_memo_ou_sans_idee(self):
        self.assertIsNone(enrichir.nettoyer_memo({"titre": "x"}, False))
        self.assertIsNone(enrichir.nettoyer_memo(memo_modele(idee=""), False))
        self.assertIsNone(enrichir.nettoyer_memo(None, False))

    def test_une_ligne_et_plafonds(self):
        reponse = memo_modele(idee="Idée\n### Fausse entrée")
        reponse["a_retenir"] = ["Ligne\n- lien : javascript:alert(1)"] * 9
        memo = enrichir.nettoyer_memo(reponse, False)
        self.assertNotIn("\n", memo["memo"]["idee"])
        self.assertEqual(len(memo["a_retenir"]), 5)
        self.assertTrue(all("\n" not in r for r in memo["a_retenir"]))

    def test_pour_toi_ignore_sans_profil(self):
        self.assertEqual(enrichir.nettoyer_memo(memo_modele(pour_toi="Pour toi."), False)["pour_toi"], "")


class Profil(unittest.TestCase):
    def test_lignes_commentaires_ignorees(self):
        with tempfile.TemporaryDirectory() as dossier:
            (Path(dossier) / enrichir.FICHIER_PROFIL).write_text(
                "# explication\n\nJe suis formateur.\n  # autre explication\nJ'aime l'IA.\n", encoding="utf-8")
            self.assertEqual(enrichir.lire_profil(dossier), "Je suis formateur.\nJ'aime l'IA.")
        self.assertEqual(enrichir.lire_profil("/dossier/inexistant"), "")

    def test_empreinte(self):
        self.assertEqual(enrichir.empreinte_profil(""), "")
        self.assertEqual(enrichir.empreinte_profil("a"), enrichir.empreinte_profil("a"))
        self.assertNotEqual(enrichir.empreinte_profil("a"), enrichir.empreinte_profil("b"))


class Memos(unittest.TestCase):
    """Mémos : nouvelles vidéos, rattrapage progressif, changement de profil."""

    def _vault(self, dossier, nb, indexees=True, profil=""):
        racine = Path(dossier)
        (racine / "raw").mkdir()
        index = ["# Index du Vault\n"]
        for i in range(nb):
            src = "https://www.instagram.com/reel/M%02d/" % i
            fiche = racine / "raw" / ("insta_M%02d.md" % i)
            fiche.write_text("---\nsource: " + src + "\nauteur: a\ntraite_le: 2026-10-01\n---\n\n# Vidéo %d\n\n"
                             "## Transcription\nLe texte de la vidéo %d.\n" % (i, i), encoding="utf-8")
            os.utime(fiche, (1000 + i, 1000 + i))
            if indexees:
                index.append("\n### Vidéo %d\n- lien : %s\n- auteur : a\n- thèmes : ia\n- contenu : Résumé %d.\n"
                             % (i, src, i))
        (racine / "index.md").write_text("".join(index), encoding="utf-8")
        if profil:
            (racine / enrichir.FICHIER_PROFIL).write_text(profil, encoding="utf-8")
        return racine

    def _lancer(self, racine, reponses, extra=()):
        appels = []

        def faux(*args, **kwargs):
            appels.append(kwargs)
            r = reponses(kwargs) if callable(reponses) else reponses
            return r
        argv = ["enrichir.py", "--vault", str(racine), "--no-pages"] + list(extra)
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "cle-de-test"}, clear=True), \
             mock.patch.object(enrichir, "demander_resume", faux), \
             mock.patch("sys.stdout"):
            code = enrichir.main()
        return code, appels

    def test_nouvelle_video_ecrit_son_memo(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault(dossier, 1, indexees=False, profil="Je forme des équipes.")
            code, appels = self._lancer(racine, memo_modele(pour_toi="Utile pour tes ateliers."))
            memo = enrichir.lire_memo(racine, "insta_M00")
        self.assertEqual(code, 0)
        self.assertEqual([a["mode"] for a in appels], ["resume"])
        self.assertIn("Je forme des équipes.", appels[0]["message"])
        self.assertEqual(memo["pour_toi"], "Utile pour tes ateliers.")
        self.assertEqual(memo["profil"], enrichir.empreinte_profil("Je forme des équipes."))

    def test_rattrapage_progressif_sans_toucher_au_resume(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault(dossier, 12)
            index_avant = (racine / "index.md").read_text(encoding="utf-8")
            reponse = memo_modele()
            del reponse["titre"]
            _, appels = self._lancer(racine, reponse)
            self.assertEqual(len(appels), enrichir.LIMITE_MEMOS)
            self.assertTrue(all(a["mode"] == "memo" for a in appels))
            self.assertEqual(len(list((racine / "memos").glob("*.json"))), enrichir.LIMITE_MEMOS)
            _, appels = self._lancer(racine, reponse)
            self.assertEqual(len(appels), 2)
            _, appels = self._lancer(racine, reponse)
            self.assertEqual(appels, [])
            self.assertEqual((racine / "index.md").read_text(encoding="utf-8"), index_avant)

    def test_video_resumee_pas_rappelee_dans_le_meme_passage(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault(dossier, 1, indexees=False)
            reponse = memo_modele()
            del reponse["memo"]          # le modèle a oublié le mémo
            _, appels = self._lancer(racine, reponse)
        self.assertEqual([a["mode"] for a in appels], ["resume"])

    def test_changement_de_profil_met_a_jour_pour_toi_seulement(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault(dossier, 1, profil="Ancien profil.")
            self._lancer(racine, memo_modele(pour_toi="Ancien conseil."))
            (racine / enrichir.FICHIER_PROFIL).write_text("Nouveau profil.", encoding="utf-8")
            _, appels = self._lancer(racine, {"pour_toi": "Nouveau conseil."})
            memo = enrichir.lire_memo(racine, "insta_M00")
        self.assertEqual([a["mode"] for a in appels], ["pour_toi"])
        self.assertIn("Nouveau profil.", appels[0]["message"])
        self.assertNotIn("Le texte de la vidéo", appels[0]["message"])
        self.assertEqual(memo["pour_toi"], "Nouveau conseil.")
        self.assertEqual(memo["memo"]["idee"], "L'idée centrale.")
        self.assertEqual(memo["profil"], enrichir.empreinte_profil("Nouveau profil."))

    def test_profil_supprime_retire_pour_toi_sans_appel(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault(dossier, 1, profil="Mon profil.")
            self._lancer(racine, memo_modele(pour_toi="Conseil."))
            (racine / enrichir.FICHIER_PROFIL).unlink()
            _, appels = self._lancer(racine, None)
            memo = enrichir.lire_memo(racine, "insta_M00")
        self.assertEqual(appels, [])
        self.assertEqual(memo["pour_toi"], "")

    def test_sans_cle_aucun_memo(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault(dossier, 2)
            argv = ["enrichir.py", "--vault", str(racine), "--no-pages"]
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch.object(enrichir, "demander_resume") as appel, mock.patch("sys.stdout"):
                self.assertEqual(enrichir.main(), 0)
            self.assertFalse(appel.called)
            self.assertFalse((racine / "memos").exists())

    def test_memo_illisible_est_refait(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self._vault(dossier, 1)
            (racine / "memos").mkdir()
            (racine / "memos" / "insta_M00.json").write_text("{pas du json", encoding="utf-8")
            self.assertIsNone(enrichir.lire_memo(racine, "insta_M00"))
            _, appels = self._lancer(racine, memo_modele())
        self.assertEqual([a["mode"] for a in appels], ["memo"])
