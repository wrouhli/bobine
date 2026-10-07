#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests de filtre.py — export Instagram, filtres.yaml, classement, parcours.

Lancement (aucune dépendance à installer) :

    python3 -m unittest discover -s tests
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import filtre  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = RACINE / "filtre.py"

URL_AAA = "https://www.instagram.com/reel/AAA111/"
URL_BBB = "https://www.instagram.com/reel/BBB222/?igsh=xyz"
URL_CCC = "https://www.instagram.com/reel/CCC333/"
URL_DDD = "https://www.instagram.com/reel/DDD444/"

CONFIG_DIRECT = """\
defaut: revoir
exclusions: []
collections:
  - nom: "Cuisine"
    garder: true
  - nom: "Mèmes"
    garder: false
themes:
  astuces:
    garder: true
    mots_cles: [astuce, astuces]
"""


def fabriquer_export(dossier):
    """Écrit un export Instagram minimal mais réaliste (mêmes formes de JSON)."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    posts = [
        {"label_values": [
            {"label": "URL", "value": URL_AAA},
            {"label": "Légende",
             "value": "La meilleure recette de tarte #cuisine #astuce"}]},
        {"label_values": [
            {"label": "URL", "value": URL_BBB},
            {"label": "LÃ©gende",
             "value": "😂 mdr le mème".encode("utf-8").decode("latin-1")}]},
        {"label_values": [
            {"label": "URL", "value": URL_CCC},
            {"label": "Légende",
             "value": "3 astuces de pro pour ranger ton bureau"}]},
        {"label_values": [
            {"label": "URL", "value": URL_DDD},
            {"label": "Légende", "value": "une pensée du jour"}]},
    ]
    collections = [
        {"label_values": [
            {"label": "Nom", "value": "Cuisine"},
            {"dict": [
                {"dict": [{"label": "URL", "value": URL_AAA}]},
            ]}]},
        {"label_values": [
            {"label": "Nom", "value": "Mèmes"},
            {"dict": [
                {"dict": [{"label": "URL", "value": URL_BBB}]},
            ]}]},
    ]
    (dossier / "saved_posts.json").write_text(
        json.dumps(posts, ensure_ascii=False), encoding="utf-8")
    (dossier / "saved_collections.json").write_text(
        json.dumps(collections, ensure_ascii=False), encoding="utf-8")
    return dossier


def lancer_filtre(dossier, *arguments):
    environ = dict(os.environ)
    environ["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(arguments),
        cwd=str(dossier), capture_output=True, text=True,
        encoding="utf-8", env=environ, timeout=60)


class AnalyseExport(unittest.TestCase):
    """charger_posts / charger_collections / localiser_export."""

    def test_posts_lus_legende_reparee(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = fabriquer_export(Path(tmp) / "export")
            posts = filtre.charger_posts(export / "saved_posts.json")
        self.assertEqual(len(posts), 4)
        self.assertEqual(posts[0]["url"], URL_AAA)
        self.assertIn("cuisine", posts[0]["hashtags"])
        self.assertIn("astuce", posts[0]["hashtags"])
        # La légende double-encodée (« LÃ©gende », mojibake) est réparée.
        self.assertEqual(posts[1]["legende"], "😂 mdr le mème")

    def test_posts_dedoublonnes_et_filtres(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            posts = [
                {"label_values": [{"label": "URL",
                                   "value": URL_AAA + "?igsh=1"}]},
                {"label_values": [{"label": "URL", "value": URL_AAA}]},
                {"label_values": [{"label": "URL", "value": "pas-une-url"}]},
                {"label_values": [{"label": "Autre", "value": "sans url"}]},
            ]
            (dossier / "saved_posts.json").write_text(
                json.dumps(posts, ensure_ascii=False), encoding="utf-8")
            lus = filtre.charger_posts(dossier / "saved_posts.json")
        self.assertEqual(len(lus), 1)
        self.assertEqual(filtre.normaliser_url(lus[0]["url"]),
                         filtre.normaliser_url(URL_AAA))

    def test_export_simplifie(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            (dossier / "saved_posts.json").write_text(
                json.dumps([{"url": URL_CCC, "caption": "hello"}],
                           ensure_ascii=False), encoding="utf-8")
            lus = filtre.charger_posts(dossier / "saved_posts.json")
        self.assertEqual(lus[0]["url"], URL_CCC)
        self.assertEqual(lus[0]["legende"], "hello")

    def test_collections_index_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = fabriquer_export(Path(tmp) / "export")
            collections, index = filtre.charger_collections(
                export / "saved_collections.json")
        self.assertEqual([c["nom"] for c in collections],
                         ["Cuisine", "Mèmes"])
        self.assertEqual(index[filtre.normaliser_url(URL_AAA)], "Cuisine")
        self.assertEqual(index[filtre.normaliser_url(URL_BBB)], "Mèmes")

    def test_localiser_export_imbrique(self):
        with tempfile.TemporaryDirectory() as tmp:
            racine = Path(tmp)
            export = fabriquer_export(racine / "zip-decompresse" / "contenu")
            dossier, posts, collections = filtre.localiser_export(racine)
        self.assertEqual(dossier, export)
        self.assertEqual(posts, export / "saved_posts.json")
        self.assertEqual(collections, export / "saved_collections.json")


class FiltresYaml(unittest.TestCase):
    """Le sous-ensemble YAML de filtres.yaml : lecture et messages clairs."""

    def test_fichier_complet(self):
        regles, avertissements = filtre.analyser_config(
            "# un commentaire\n"
            "defaut: garder\n"
            "\n"
            "exclusions: [pub, \"promo spéciale, urgente\"]\n"
            "\n"
            "collections:\n"
            "  - nom: \"Cuisine\"\n"
            "    garder: true\n"
            "  - nom: 'Éco'          # commentaire après la valeur\n"
            "    garder: non\n"
            "  - nom: \"Sans réglage\"\n"
            "\n"
            "themes:\n"
            "  astuces:\n"
            "    garder: oui\n"
            "    mots_cles: [astuce, astuces]\n"
            "  memes:\n"
            "    garder: false\n"
            "    mots_cles:\n"
            "      - meme\n"
            "      - memes\n")
        self.assertEqual(avertissements, [])
        self.assertEqual(regles["defaut"], "garder")
        self.assertEqual(regles["exclusions"],
                         ["pub", "promo spéciale, urgente"])
        self.assertEqual(len(regles["collections"]), 3)
        self.assertEqual(regles["collections"][0],
                         {"nom": "Cuisine", "garder": True})
        self.assertEqual(regles["collections"][1],
                         {"nom": "Éco", "garder": False})
        self.assertTrue(regles["collections"][2]["garder"])
        self.assertEqual(regles["themes"]["astuces"]["mots_cles"],
                         ["astuce", "astuces"])
        self.assertEqual(regles["themes"]["memes"]["garder"], False)
        self.assertEqual(regles["themes"]["memes"]["mots_cles"],
                         ["meme", "memes"])

    def test_vide_et_commentaires(self):
        defauts = {"defaut": "revoir", "exclusions": [],
                   "collections": [], "themes": {}}
        regles, avertissements = filtre.analyser_config("")
        self.assertEqual(regles, defauts)
        self.assertEqual(avertissements, [])
        regles, _ = filtre.analyser_config("# rien\n\n# que des commentaires\n")
        self.assertEqual(regles, defauts)

    def test_themes_laisse_vide(self):
        # « themes: » sans contenu vaut None — surtout pas un plantage.
        regles, _ = filtre.analyser_config("themes:\n")
        self.assertEqual(regles["themes"], {})

    def test_guillemets_et_emoji(self):
        regles, _ = filtre.analyser_config(
            "collections:\n"
            "  - nom: \"💡 Astuces : les bases\"\n"
            "    garder: true\n")
        self.assertEqual(regles["collections"][0]["nom"],
                         "💡 Astuces : les bases")
        self.assertEqual(filtre.normaliser_nom("💡 Astuces : les bases"),
                         filtre.normaliser_nom("Astuces les bases"))
        self.assertEqual(filtre.normaliser_nom("Économie"), "economie")

    def test_booleen_invalide(self):
        with self.assertRaises(filtre.ErreurFiltre) as capture:
            filtre.analyser_config("collections:\n"
                                   "  - nom: \"X\"\n"
                                   "    garder: vraii\n")
        self.assertIn("true ou false", str(capture.exception))

    def test_tabulation_refusee(self):
        with self.assertRaises(filtre.ErreurFiltre) as capture:
            filtre.analyser_config("defaut: revoir\n\tgarder: true\n")
        self.assertIn("tabulation", str(capture.exception).lower())
        # Une ligne d'espaces (ou tabulations) toute seule ne gêne pas.
        regles, _ = filtre.analyser_config("defaut: revoir\n\t\n   \n")
        self.assertEqual(regles["defaut"], "revoir")

    def test_clef_inconnue(self):
        with self.assertRaises(filtre.ErreurFiltre) as capture:
            filtre.analyser_config("colletion: []\n")
        self.assertIn("clef inconnue", str(capture.exception))

    def test_defaut_invalide(self):
        with self.assertRaises(filtre.ErreurFiltre):
            filtre.analyser_config("defaut: peutetre\n")

    def test_garder_manquant_vaut_true(self):
        regles, _ = filtre.analyser_config("collections:\n"
                                           "  - nom: \"Cuisine\"\n")
        self.assertTrue(regles["collections"][0]["garder"])

    def test_fins_de_ligne_windows(self):
        regles, _ = filtre.analyser_config(
            "defaut: garder\r\nexclusions: []\r\n")
        self.assertEqual(regles["defaut"], "garder")

    def test_avertissement_reglage_inconnu(self):
        regles, avertissements = filtre.analyser_config(
            "themes:\n"
            "  astuces:\n"
            "    garder: true\n"
            "    theme: cuisine\n")
        self.assertTrue(any("theme" in a for a in avertissements))

    def test_exemple_du_repo_est_valide(self):
        texte = (RACINE / "filtres.exemple.yaml").read_text(encoding="utf-8")
        regles, avertissements = filtre.analyser_config(texte)
        self.assertEqual(avertissements, [])
        self.assertEqual(regles["defaut"], "revoir")
        self.assertEqual(len(regles["collections"]), 4)


class Classement(unittest.TestCase):
    """classer / correspond : la collection fait foi, le rejet gagne."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        export = fabriquer_export(Path(cls._tmp.name) / "export")
        cls.posts = {filtre.normaliser_url(p["url"]): p
                     for p in filtre.charger_posts(
                         export / "saved_posts.json")}
        cls.collections, cls.index = filtre.charger_collections(
            export / "saved_collections.json")
        cls.regles, _ = filtre.analyser_config(CONFIG_DIRECT)
        cls.table = filtre.table_collections(cls.regles)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def classer(self, url, regles=None, table=None):
        regles = regles or self.regles
        table = table if table is not None else self.table
        return filtre.classer(self.posts[filtre.normaliser_url(url)],
                              regles, table, self.index)

    def test_collection_fait_foi(self):
        verdict, motif = self.classer(URL_AAA)
        self.assertEqual(verdict, "garder")
        self.assertIn("Cuisine", motif)

    def test_collection_ecartee(self):
        verdict, motif = self.classer(URL_BBB)
        self.assertEqual(verdict, "ecarter")
        self.assertIn("Mèmes", motif)

    def test_collection_hors_config(self):
        regles, _ = filtre.analyser_config(
            "collections:\n  - nom: \"Cuisine\"\n    garder: true\n")
        verdict, motif = self.classer(URL_BBB, regles=regles,
                                      table=filtre.table_collections(regles))
        self.assertEqual(verdict, "revoir")
        self.assertIn("hors config", motif)

    def test_exclusion_prioritaire_sur_collection(self):
        regles, _ = filtre.analyser_config(
            "exclusions: [tarte]\n"
            "collections:\n  - nom: \"Cuisine\"\n    garder: true\n")
        verdict, motif = self.classer(URL_AAA, regles=regles,
                                      table=filtre.table_collections(regles))
        self.assertEqual(verdict, "ecarter")
        self.assertEqual(motif, "exclusion")

    def test_theme_garde_sans_collection(self):
        verdict, motif = self.classer(URL_CCC)
        self.assertEqual(verdict, "garder")
        self.assertIn("astuces", motif)

    def test_theme_ecarte_sans_collection(self):
        regles, _ = filtre.analyser_config(
            "themes:\n"
            "  pensees:\n"
            "    garder: false\n"
            "    mots_cles: [pensée, pensées]\n")
        verdict, motif = self.classer(URL_DDD, regles=regles,
                                      table=filtre.table_collections(regles))
        self.assertEqual(verdict, "ecarter")
        self.assertIn("pensees", motif)

    def test_non_classe_reste_a_revoir(self):
        verdict, motif = self.classer(URL_DDD)
        self.assertEqual(verdict, "revoir")
        self.assertEqual(motif, "non classé")

    def test_mots_courts_hashtag_seulement(self):
        post = {"url": URL_DDD, "legende": "il fait frais dehors",
                "hashtags": [], "texte": "il fait frais dehors"}
        self.assertFalse(filtre.correspond(post, "ai"))
        self.assertTrue(filtre.correspond(post, "frais"))
        post_hashtag = {"url": URL_DDD, "legende": "solution #ai",
                        "hashtags": ["ai"], "texte": "solution #ai"}
        self.assertTrue(filtre.correspond(post_hashtag, "ai"))
        self.assertTrue(filtre.correspond(post_hashtag, "#ai"))
        self.assertTrue(filtre.correspond(post_hashtag, "AI"))


class ParcoursComplet(unittest.TestCase):
    """filtre.py de bout en bout : --init-config → édition → --rapport → sortie."""

    def test_init_puis_rapport_puis_sortie(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            export = fabriquer_export(tmp / "export")
            config = tmp / "filtres.yaml"
            journal = tmp / "journal.json"
            args = ["--export", str(export), "--config", str(config),
                    "--journal", str(journal)]

            resultat = lancer_filtre(tmp, *(args + ["--init-config"]))
            self.assertEqual(resultat.returncode, 0,
                             resultat.stdout + resultat.stderr)
            self.assertTrue(config.exists())
            texte = config.read_text(encoding="utf-8")
            self.assertIn('"Cuisine"', texte)
            self.assertIn('"Mèmes"', texte)

            # L'utilisateur trie : Mèmes dehors, thème astuces activé.
            texte = texte.replace('  - nom: "Mèmes"\n    garder: true',
                                  '  - nom: "Mèmes"\n    garder: false')
            texte = texte.replace(
                "  # astuces:\n  #   garder: true\n"
                "  #   mots_cles: [astuce, astuces, tips]",
                "  astuces:\n    garder: true\n"
                "    mots_cles: [astuce, astuces]")
            config.write_text(texte, encoding="utf-8")

            resultat = lancer_filtre(tmp, *(args + ["--rapport"]))
            self.assertEqual(resultat.returncode, 0,
                             resultat.stdout + resultat.stderr)
            ingeres = re.search(r"à ingérer après filtre\s*: (\d+)",
                                resultat.stdout)
            assert ingeres is not None, resultat.stdout
            self.assertEqual(ingeres.group(1), "2")
            self.assertIn("thème « astuces »", resultat.stdout)
            self.assertIn("collection « Mèmes »", resultat.stdout)
            self.assertFalse((tmp / "liens-filtres.txt").exists())

            resultat = lancer_filtre(tmp, *args)
            self.assertEqual(resultat.returncode, 0,
                             resultat.stdout + resultat.stderr)
            liens = (tmp / "liens-filtres.txt").read_text(
                encoding="utf-8").split()
            self.assertEqual(liens, [URL_AAA, URL_CCC])

    def test_journal_ignore_les_deja_ingeres(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            export = fabriquer_export(tmp / "export")
            config = tmp / "filtres.yaml"
            config.write_text(CONFIG_DIRECT, encoding="utf-8")
            journal = tmp / "journal.json"
            # Sans « / » final et sans query : la forme doit être reconnue.
            journal.write_text(json.dumps(
                {"https://www.instagram.com/reel/AAA111":
                 {"statut": "ok", "fiche": "insta_AAA111.md"}},
                ensure_ascii=False), encoding="utf-8")

            resultat = lancer_filtre(tmp, "--export", str(export),
                                     "--config", str(config),
                                     "--journal", str(journal))
            self.assertEqual(resultat.returncode, 0,
                             resultat.stdout + resultat.stderr)
            deja = re.search(r"déjà ingérés \(journal\)\s*: (\d+)",
                             resultat.stdout)
            assert deja is not None, resultat.stdout
            self.assertEqual(deja.group(1), "1")
            liens = (tmp / "liens-filtres.txt").read_text(
                encoding="utf-8").split()
            self.assertEqual(liens, [URL_CCC])

    def test_defaut_garder_inclut_les_non_classes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            export = fabriquer_export(tmp / "export")
            config = tmp / "filtres.yaml"
            config.write_text(CONFIG_DIRECT.replace("defaut: revoir",
                                                    "defaut: garder"),
                              encoding="utf-8")
            resultat = lancer_filtre(tmp, "--export", str(export),
                                     "--config", str(config),
                                     "--journal", str(tmp / "journal.json"))
            self.assertEqual(resultat.returncode, 0,
                             resultat.stdout + resultat.stderr)
            liens = (tmp / "liens-filtres.txt").read_text(
                encoding="utf-8").split()
            self.assertEqual(liens, [URL_AAA, URL_CCC, URL_DDD])

    def test_liste_collections(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            export = fabriquer_export(tmp / "export")
            config = tmp / "filtres.yaml"
            config.write_text(CONFIG_DIRECT, encoding="utf-8")
            resultat = lancer_filtre(tmp, "--export", str(export),
                                     "--config", str(config),
                                     "--liste-collections")
            self.assertEqual(resultat.returncode, 0,
                             resultat.stdout + resultat.stderr)
            self.assertIn("GARDER", resultat.stdout)
            self.assertIn("ÉCARTER", resultat.stdout)
            self.assertIn("Mèmes", resultat.stdout)

    def test_init_config_necrase_pas_sans_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            export = fabriquer_export(tmp / "export")
            config = tmp / "filtres.yaml"
            args = ["--export", str(export), "--config", str(config),
                    "--init-config"]
            self.assertEqual(lancer_filtre(tmp, *args).returncode, 0)
            resultat = lancer_filtre(tmp, *args)
            self.assertEqual(resultat.returncode, 1)
            self.assertIn("existe déjà", resultat.stdout)


class SansReseau(unittest.TestCase):
    """La promesse « tout est local » : aucune bibliothèque réseau."""

    def test_filtre_ne_contacte_rien(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for mot in ("urllib", "requests", "socket", "urlopen", "http.client"):
            self.assertNotIn(mot, source)


if __name__ == "__main__":
    unittest.main()
