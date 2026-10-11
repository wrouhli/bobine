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



def vault_demo(dossier, config="CARTE=non\nSYNC_ICLOUD=non\n"):
    """Un petit vault fictif : deux vidéos liées, une en attente, une sans parole."""
    racine = Path(dossier)
    (racine / "raw").mkdir()
    (racine / "config.env").write_text(config, encoding="utf-8")
    fiches = [
        ("yt_relance01", "https://www.youtube.com/watch?v=relance01", "2026-10-10", 754,
         "Trois relances", "Ma description\nsur deux lignes",
         "Premier point important. Deuxième point. Troisième point. Quatrième point <script>alert(1)</script>.",
         ["e-mail", "fidélisation"], "Un résumé clair."),
        ("insta_avis01", "https://www.instagram.com/reel/avis01/", "2026-10-08", 40,
         "Demander un avis", "(vide)", "Le bon moment pour demander un avis.",
         ["fidélisation"], "Un autre résumé."),
        ("insta_musique", "https://www.instagram.com/reel/musique/", "2026-10-02", 20,
         "Ambiance", "Petite vibe", "(pas de texte récupéré)", ["organisation"], "Sans parole."),
        ("insta_attente", "https://www.instagram.com/reel/attente/", "2026-10-11", 62,
         "En attente", "(vide)", "Une transcription déjà là.", ["(en attente)"], None),
    ]
    index = ["# Index du Vault\n"]
    for nom, src, date, duree, titre, desc, tr, themes, resume in fiches:
        (racine / "raw" / (nom + ".md")).write_text(
            "---\nsource: " + src + "\nauteur: Testeur\nduree_s: " + str(duree)
            + "\ntraite_le: " + date + "\n---\n\n# " + titre + "\n\n## Description\n" + desc
            + "\n\n## Transcription\n" + tr + "\n\n## Liens\n[[ne pas afficher]]\n",
            encoding="utf-8")
        contenu = resume or "(résumé en attente : ta vidéo est enregistrée ; Bobine réessaiera automatiquement)"
        index.append("\n### " + titre + "\n- lien : " + src + "\n- auteur : Testeur\n- thèmes : "
                     + ", ".join(themes) + "\n- contenu : " + contenu + "\n")
    (racine / "index.md").write_text("".join(index), encoding="utf-8")
    return racine


def generer(racine):
    with mock.patch.object(sys, "argv", ["generate_page.py", "--vault", str(racine)]):
        with mock.patch("sys.stdout"):
            generate_page.main()
    return (racine / "vault.html").read_text(encoding="utf-8")


class FicheComplete(unittest.TestCase):
    """Étape 1 de la refonte : chaque vidéo a sa fiche complète dans la page."""

    def test_une_fiche_par_video_avec_transcription(self):
        with tempfile.TemporaryDirectory() as dossier:
            page = generer(vault_demo(dossier))
        self.assertEqual(page.count('class="carte"'), 4)
        self.assertEqual(page.count('<article class="fiche"'), 4)
        for id_ in ("f-yt_relance01", "f-insta_avis01", "f-insta_musique", "f-insta_attente"):
            self.assertIn('id="' + id_ + '"', page)
            self.assertIn('href="#' + id_ + '"', page)
        self.assertIn("Premier point important.", page)
        self.assertIn("Ma description\nsur deux lignes", page)
        self.assertIn("13 min", page)
        self.assertNotIn("ne pas afficher", page)

    def test_transcription_echappee(self):
        with tempfile.TemporaryDirectory() as dossier:
            page = generer(vault_demo(dossier))
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_video_en_attente_et_sans_parole(self):
        with tempfile.TemporaryDirectory() as dossier:
            page = generer(vault_demo(dossier))
        bibliotheque = page.split('<article class="fiche"')[0]
        self.assertIn("Résumé à venir", bibliotheque)
        self.assertNotIn("(résumé en attente", bibliotheque)
        self.assertNotIn('data-t="(en attente)"', page)
        self.assertIn("Une transcription déjà là.", page)
        self.assertIn("Pas de transcription", page)

    def test_videos_liees_par_themes(self):
        with tempfile.TemporaryDirectory() as dossier:
            page = generer(vault_demo(dossier))
        fiche = page.split('id="f-yt_relance01"')[1].split("</article>")[0]
        self.assertIn('href="#f-insta_avis01"', fiche)
        self.assertNotIn('href="#f-insta_musique"', fiche)

    def test_lecture_sans_javascript_et_sans_ressource_externe(self):
        with tempfile.TemporaryDirectory() as dossier:
            page = generer(vault_demo(dossier))
        self.assertIn(".fiche:target{display:block}", page)
        self.assertNotRegex(page, r"<link[^>]+href=[\"']https?://")
        self.assertNotRegex(page, r"<script[^>]+src=")
        self.assertNotIn("@import", page)
        self.assertNotRegex(page, r"url\(\s*['\"]?https?://")
        self.assertNotRegex(page.lower(), r"6c4dff|8b6dff")

    @unittest.skipUnless(__import__("importlib").util.find_spec("numpy"), "numpy requis pour la carte")
    def test_carte_sans_transcriptions_et_avec_lien_vers_la_fiche(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = vault_demo(dossier, "CARTE=oui\nSYNC_ICLOUD=non\n")
            generer(racine)
            carte = (racine / "graph.html").read_text(encoding="utf-8")
        self.assertNotIn("Premier point important", carte)
        self.assertIn('"id": "f-yt_relance01"', carte)
        self.assertIn("ap-fiche", carte)


class OutilsFiche(unittest.TestCase):
    def test_paragraphes_avec_ponctuation(self):
        texte = "Un. Deux. Trois. Quatre. Cinq."
        self.assertEqual(generate_page.paragraphes(texte), ["Un. Deux. Trois.", "Quatre. Cinq."])

    def test_paragraphes_sans_ponctuation(self):
        texte = " ".join("mot%d" % i for i in range(150))
        morceaux = generate_page.paragraphes(texte)
        self.assertEqual(len(morceaux), 3)
        self.assertTrue(all(len(m.split()) <= 70 for m in morceaux))
        self.assertEqual(" ".join(morceaux), texte)

    def test_ancien_titre_transcription_audio(self):
        # Les fiches créées avec l'ancien format titrent « ## Transcription audio ».
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "insta_ancien.md"
            chemin.write_text(
                "---\nsource: https://www.instagram.com/reel/ancien/\ntraite_le: 2026-09-01\n---\n\n"
                "# Ancienne fiche\n\n## Description\nUne description.\n\n"
                "## Transcription audio\nLe texte de la vidéo est bien là.\n\n## Liens\n[[x]]\n",
                encoding="utf-8")
            fiche = generate_page.lire_fiche_brute(chemin)
        self.assertEqual(fiche["transcription"], "Le texte de la vidéo est bien là.")
        self.assertEqual(fiche["description"], "Une description.")

    def test_ancien_titre_visible_dans_la_page(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = vault_demo(dossier)
            ancienne = racine / "raw" / "insta_avis01.md"
            ancienne.write_text(ancienne.read_text(encoding="utf-8")
                                .replace("## Transcription\n", "## Transcription audio\n"),
                                encoding="utf-8")
            page = generer(racine)
        fiche = page.split('id="f-insta_avis01"')[1].split("</article>")[0]
        self.assertIn("Le bon moment pour demander un avis.", fiche)
        self.assertNotIn("Pas de transcription", fiche)

    def test_sections_reconnues(self):
        self.assertEqual(generate_page.section_connue("Transcription"), "transcription")
        self.assertEqual(generate_page.section_connue("  transcription   AUDIO "), "transcription")
        self.assertEqual(generate_page.section_connue("Description"), "description")
        self.assertIsNone(generate_page.section_connue("Liens"))
        self.assertIsNone(generate_page.section_connue("Transcriptions diverses"))

    def test_duree_lisible(self):
        self.assertEqual(generate_page.duree_lisible("754.2"), "13 min")
        self.assertEqual(generate_page.duree_lisible("42"), "42 s")
        self.assertEqual(generate_page.duree_lisible(""), "")

    def test_identifiants_uniques(self):
        entrees = [{"titre": "a", "lien": "https://www.instagram.com/reel/X/", "fichier": ""},
                   {"titre": "b", "lien": "https://www.instagram.com/reel/X/?igsh=1", "fichier": ""}]
        ids = [e["id"] for e in generate_page.attribuer_ids(entrees)]
        self.assertEqual(len(set(ids)), 2)


if __name__ == "__main__":
    unittest.main()
