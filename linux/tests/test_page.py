#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests de generate_page.py (et graphe.py) — liens sûrs, repères, lecture de l'index.

Lancement (aucune dépendance à installer) :

    python3 -m unittest discover -s tests
"""

import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
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
        self.assertIn(".fiche:target,.vue-profil:target{display:block}", page)
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



def ecrire_memo_demo(racine, nom, pour_toi="", idee="Idée centrale de la vidéo."):
    import json
    (racine / "memos").mkdir(exist_ok=True)
    (racine / "memos" / (nom + ".json")).write_text(json.dumps({
        "version": 1, "a_retenir": ["Premier réflexe.", "Second réflexe."],
        "memo": {"idee": idee, "points": ["Un point clé."], "etapes": ["Étape A."], "outils": ["Outil B"]},
        "pour_toi": pour_toi, "profil": "x"}), encoding="utf-8")


class MemoEtProfil(unittest.TestCase):
    """Étape 2 : mémo, « À retenir », « Pour toi » et page Profil."""

    def test_memo_a_retenir_et_pour_toi(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = vault_demo(dossier)
            (racine / "Mon profil.txt").write_text("# aide\nJe forme des équipes.\n", encoding="utf-8")
            ecrire_memo_demo(racine, "yt_relance01", pour_toi="Utile pour tes ateliers.")
            page = generer(racine)
        fiche = page.split('id="f-yt_relance01"')[1].split("</article>")[0]
        self.assertIn('data-niveau="memo"', fiche)
        self.assertIn("Idée centrale de la vidéo.", fiche)
        self.assertIn("Étape A.", fiche)
        self.assertIn('<span class="num">2</span><span>Second réflexe.</span>', fiche)
        self.assertIn("Utile pour tes ateliers.", fiche)
        autre = page.split('id="f-insta_avis01"')[1].split("</article>")[0]
        self.assertNotIn('data-niveau="memo"', autre)
        self.assertNotIn("Pour toi", autre)

    def test_invitation_au_profil_quand_il_manque(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = vault_demo(dossier)
            ecrire_memo_demo(racine, "yt_relance01")
            page = generer(racine)
        fiche = page.split('id="f-yt_relance01"')[1].split("</article>")[0]
        self.assertIn('href="#profil"', fiche)
        self.assertIn("Pas encore de profil", page)

    def test_memo_abime_ignore_et_texte_echappe(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = vault_demo(dossier)
            (racine / "memos").mkdir()
            (racine / "memos" / "insta_avis01.json").write_text("{abîmé", encoding="utf-8")
            ecrire_memo_demo(racine, "yt_relance01", idee="<img src=x onerror=alert(1)>")
            (racine / "Mon profil.txt").write_text("<b>moi</b>", encoding="utf-8")
            page = generer(racine)
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", page)
        self.assertNotIn("<b>moi</b>", page)
        self.assertIn("&lt;b&gt;moi&lt;/b&gt;", page)
        autre = page.split('id="f-insta_avis01"')[1].split("</article>")[0]
        self.assertNotIn('data-niveau="memo"', autre)

    def test_recherche_inclut_a_retenir(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = vault_demo(dossier)
            ecrire_memo_demo(racine, "yt_relance01")
            page = generer(racine)
        carte = page.split('data-fiche="f-yt_relance01"')[1].split("</a>")[0]
        self.assertIn("Premier réflexe.", carte)



class BalisesPage(HTMLParser):
    """Inspecte le HTML livré, sans navigateur ni dépendance supplémentaire."""

    def __init__(self, page):
        super().__init__()
        self.balises = []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        self.balises.append((tag, dict(attrs)))

    def par_id(self, id_):
        return next(attrs for _, attrs in self.balises if attrs.get("id") == id_)


def script_demander(page):
    return page.split("/* ---- Demander : état privé à l'onglet, aucune persistance ---- */", 1)[1].split(
        "/* ---- fin Demander ---- */", 1)[0]


class DemanderStatique(unittest.TestCase):
    """La page copiée hors serveur reste une bibliothèque, pas un chat inerte."""

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        self.racine = vault_demo(self.dossier.name)
        self.page = generer(self.racine)
        self.html = BalisesPage(self.page)
        self.js = script_demander(self.page)

    def test_acces_tous_caches_et_question_inactive_par_defaut(self):
        acces = [(tag, a) for tag, a in self.html.balises if "demander-acces" in a.get("class", "").split()]
        self.assertEqual(len(acces), 5)  # navigation + chaque fiche, même en attente
        for tag, attrs in acces:
            self.assertEqual(tag, "a")
            self.assertEqual(attrs["href"], "#demander")
            self.assertIn("hidden", attrs)
        self.assertIn("hidden", self.html.par_id("demander"))
        self.assertIn("disabled", self.html.par_id("demander-question"))
        self.assertIn("disabled", self.html.par_id("demander-envoyer"))
        self.assertIn("[hidden]{display:none !important}", self.page)
        self.assertNotIn("#demander:target", self.page)
        self.assertIn("body.demander-ouvert #bibliotheque", self.page)

    def test_fiches_reelles_et_selection_non_interpolee_en_javascript(self):
        ids = {a["id"] for tag, a in self.html.balises if tag == "article" and a.get("class") == "fiche"}
        actions = {a["data-demander-fiche"] for _, a in self.html.balises if "data-demander-fiche" in a}
        self.assertEqual(ids, actions)
        self.assertEqual(self.page.count("Poser une question sur cette vidéo"), 4)
        self.assertIn('id="demander-selection">Toute la bibliothèque', self.page)
        self.assertIn('id="demander-global"', self.page)
        self.assertNotIn("Trois relances", self.js)

    def test_menu_et_mobile_deux_rangees(self):
        nav = self.page.split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]
        self.assertLess(nav.index("Bibliothèque"), nav.index("Demander"))
        self.assertLess(nav.index("Demander"), nav.index("Profil"))
        self.assertIn(".nav{order:3;width:100%;justify-content:center}", self.page)
        self.assertIn(".tete-in{gap:8px;padding:10px 14px;flex-wrap:wrap}", self.page)

    def test_aucun_appel_en_file_et_origine_unique(self):
        garde = 'if (location.protocol !== "http:" && location.protocol !== "https:") { return; }'
        self.assertIn(garde, self.js)
        self.assertLess(self.js.index(garde), self.js.index("fetch("))
        self.assertEqual(re.findall(r'requeteJSON\("([^"]+)"', self.js), ["/api/bobine", "/api/demander"])
        for option in ('credentials: "same-origin"', 'mode: "same-origin"', 'cache: "no-store"', 'redirect: "error"'):
            self.assertIn(option, self.js)
        self.assertNotRegex(self.js, r"localhost|127\.0\.0\.1|https?://|XMLHttpRequest|sendBeacon|WebSocket")

    def test_sorties_texte_uniquement_et_ancres_verifiees(self):
        for interdit in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "source.lien", "source.href", "source.url"):
            self.assertNotIn(interdit, self.js)
        self.assertIn("contenu.textContent = texte", self.js)
        self.assertIn("lien.textContent =", self.js)
        self.assertIn("/^#f-[A-Za-z0-9_-]+$/", self.js)
        self.assertIn('source.ancre !== "#" + source.id', self.js)
        self.assertNotIn("!fiches.has(source.id)", self.js)
        self.assertIn('locale ? source.ancre : "vault.html" + source.ancre', self.js)
        self.assertIn('lien.setAttribute("target", "_blank")', self.js)
        self.assertIn('lien.setAttribute("rel", "noopener noreferrer")', self.js)
        self.assertIn("white-space:pre-wrap", self.page)

    def test_historique_borne_sans_stockage_et_exemples_sans_envoi(self):
        self.assertNotRegex(self.js, r"localStorage|sessionStorage|indexedDB|document\.cookie")
        self.assertIn("historique.slice(-6)", self.js)
        self.assertIn("content: texte.slice(0, 800)", self.js)
        self.assertIn("content: resultat.reponse.slice(0, 800)", self.js)
        exemples = self.js.split('exemples.forEach(function(b){ b.addEventListener("click"', 1)[1].split("}); });", 1)[0]
        self.assertNotIn("envoyer(", exemples)
        self.assertNotIn("fetch(", exemples)
        self.assertNotIn("requeteJSON(", exemples)
        self.assertEqual(self.html.par_id("demander-question")["maxlength"], "2000")

    def test_exemples_issus_du_dom_et_aide_selection_stricte(self):
        self.assertIn('document.querySelectorAll("#chips .chip[data-t]")', self.js)
        self.assertIn('querySelectorAll(".themes-fiche [data-filtre]")', self.js)
        self.assertIn('b.textContent = b.dataset.question', self.js)
        self.assertNotIn('data-question="', self.page)
        self.assertIn('data-t="fidélisation"', self.page)
        self.assertIn('data-t="e-mail"', self.page)
        self.assertIn("Ouvre une fiche pour poser une question", self.page)
        self.assertIn("limite les réponses à cette vidéo uniquement", self.page)
        self.assertIn("sans chercher dans les autres fiches", self.js)
        self.assertIn('id="demander-aide-selection">Bobine cherche dans toute ta bibliothèque.', self.page)

    def test_demander_reste_francais_sans_cadratin(self):
        section = self.page.split('<section class="vue-demander"', 1)[1].split('</section>', 1)[0]
        self.assertNotIn("—", section + self.js)
        for ancien in ("Des idées pour cette semaine", "Les conseils qui reviennent", "Un premier pas concret"):
            self.assertNotIn(ancien, section)
        for anglais in ("Try again", "Retry later", "Daily quota", "Rate limit", "New conversation"):
            self.assertNotIn(anglais, section + self.js)

    def test_accessibilite_et_double_envoi(self):
        self.assertEqual(self.html.par_id("demander")["aria-labelledby"], "demander-titre")
        self.assertEqual(self.html.par_id("demander-statut")["role"], "status")
        self.assertEqual(self.html.par_id("demander-statut")["aria-live"], "polite")
        self.assertIn("if (enCours || verification || !jeton) { return; }", self.js)
        self.assertIn('formulaire.setAttribute("aria-busy"', self.js)
        self.assertIn('if (ouverte && prendreFocus) { titre.focus(); }', self.js)
        self.assertIn('ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)', self.js)

    def test_profil_readonly_et_fichiers_source_inchanges(self):
        (self.racine / "Mon profil.txt").write_text("Je forme des équipes.", encoding="utf-8")
        ecrire_memo_demo(self.racine, "yt_relance01", pour_toi="Utile pour tes ateliers.")
        fichiers = [self.racine / "Mon profil.txt", self.racine / "memos/yt_relance01.json"]
        avant = [p.read_bytes() for p in fichiers]
        page = generer(self.racine)
        profil = page.split('<section class="vue-profil"', 1)[1].split("</section>", 1)[0]
        self.assertNotRegex(profil, r"<(?:form|input|textarea|button)\b|contenteditable")
        self.assertEqual(avant, [p.read_bytes() for p in fichiers])
        self.assertNotRegex(self.js, r"/api/(?:profil|memos|pourtoi)")

    def test_titre_piege_secret_absent_et_pas_de_ressources_externes(self):
        piege = '<img src=x onerror="alert(1)"> __FICHES__ </script>'
        index = self.racine / "index.md"
        index.write_text(index.read_text(encoding="utf-8").replace("Trois relances", piege), encoding="utf-8")
        config = self.racine / "config.env"
        config.write_text(config.read_text(encoding="utf-8") + "OPENAI_API_KEY=secret-ne-jamais-copier\n", encoding="utf-8")
        page = generer(self.racine)
        self.assertNotIn('<img src=x', page)
        self.assertIn('&lt;img src=x onerror=&quot;alert(1)&quot;&gt; __FICHES__ &lt;/script&gt;', page)
        self.assertNotIn("secret-ne-jamais-copier", page)
        self.assertNotRegex(page, r'<(?:script|link)[^>]+(?:src|href)="https?://')
        self.assertNotIn("@import", page)

    def test_copies_linux_identiques_octet_par_octet(self):
        racine = Path(__file__).resolve().parent.parent
        if racine.name == "linux":
            racine = racine.parent
        for nom in ("generate_page.py", "tests/test_page.py"):
            self.assertEqual((racine / nom).read_bytes(), (racine / "linux" / nom).read_bytes(), nom)


# Exécution facultative du JS dans Node avec un petit DOM et fetch simulés.
# Aucun réseau ni bibliothèque npm : même les expirations sont simulées.
HARNAIS_DEMANDER = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const entree = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Element {
  constructor(tag='div', id='') {
    this.tagName=tag; this.id=id; this.attrs={}; this.dataset={}; this.children=[];
    this.hidden=true; this.disabled=false; this.value=''; this.textContent=''; this.listeners={};
    const classes=new Set(); this.classList={toggle:(c,b)=>b?classes.add(c):classes.delete(c), contains:c=>classes.has(c)};
  }
  setAttribute(k,v) { this.attrs[k]=v; }
  getAttribute(k) { return this.attrs[k]; }
  removeAttribute(k) { delete this.attrs[k]; }
  appendChild(e) { this.children.push(e); return e; }
  removeChild(e) { this.children.splice(this.children.indexOf(e),1); }
  get firstChild() { return this.children[0]; }
  querySelector(q) { assert.equal(q,'h1'); return {textContent:this.titre}; }
  querySelectorAll(q) {
    assert.equal(q,'.themes-fiche [data-filtre]');
    return (this.themes||[]).map(t=>{const p=new Element('a');p.dataset.filtre=t;return p;});
  }
  addEventListener(e,fn) { (this.listeners[e] ||= []).push(fn); }
  emit(e,extra={}) { return Promise.all((this.listeners[e]||[]).map(fn=>fn({preventDefault(){}, ...extra}))); }
  focus() { this.focused=true; }
}
const pause = () => new Promise(resolve=>setImmediate(resolve));
const valide = {disponible:true,jeton:'jeton-de-test-1234567890'};
function environnement({protocol='http:',etat=valide,hash='#demander',discoveryStatus=200,
  themes=['fidélisation','e-mail','organisation'],themesFiche=['e-mail'],avecFiche=true,
  titreFiche='<img onerror=x> Titre de test'}={}) {
  const noms=['demander','demander-titre','demander-form','demander-question','demander-envoyer','demander-nouveau',
    'demander-global','demander-selection','demander-messages','demander-statut','demander-reconnecter',
    'demander-exemples','demander-aide-selection'];
  const ids=Object.fromEntries(noms.map(id=>[id,new Element('div',id)]));
  ids['demander-envoyer'].disabled=ids['demander-question'].disabled=true;
  const nav=['#bibliotheque','#demander','#profil'].map(h=>{const a=new Element('a');a.attrs.href=h;return a;});
  const fiche=new Element('article','f-yt_test01'); fiche.titre=titreFiche;fiche.themes=themesFiche;
  const action=new Element('a'); action.dataset.demanderFiche=fiche.id;
  const chips=['',...themes].map(t=>{const p=new Element('button');p.dataset.t=t;return p;});
  const acces=[nav[1],action], calls=[], queue=[{json:etat,status:discoveryStatus}], timers=new Map();
  const win=new Element(), location={protocol,hash};
  let timerId=0;
  const fakeFetch=(url,options)=>{
    calls.push({url,options});
    assert.ok(queue.length, 'Un appel réseau imprévu a été tenté');
    const r=queue.shift();
    if (r.error) return Promise.reject(r.error);
    if (r.pending) return new Promise((resolve,reject)=>{
      r.resolve=json=>resolve({ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>json});
      options.signal.addEventListener('abort',()=>{const e=new Error('délai');e.name='AbortError';reject(e);});
    });
    return Promise.resolve({ok:(r.status||200)>=200 && (r.status||200)<300,status:r.status||200,
      headers:{get:k=>k.toLowerCase()==='retry-after' ? (r.retryAfter??null) : (r.contentType??'application/json; charset=utf-8')},
      json:async()=>{if(r.jsonError) {throw new SyntaxError('Traceback secret');} return r.json;}});
  };
  win.fetch=fakeFetch; win.AbortController=AbortController;
  const document={body:new Element('body'),getElementById:id=>{assert.ok(ids[id],id);return ids[id];},
    createElement:tag=>new Element(tag),querySelectorAll:q=>{
      const valeurs={'.demander-acces':acces,'#chips .chip[data-t]':chips,'.nav a':nav,'article.fiche':avecFiche?[fiche]:[]};
      assert.ok(valeurs[q],q);return valeurs[q];
    }};
  vm.runInNewContext(entree.js,{window:win,document,location,fetch:fakeFetch,AbortController,
    setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id)});
  return {ids,nav,fiche,action,acces,calls,queue,win,location,timers,
    get exemple(){return ids['demander-exemples'].children.find(b=>b.tagName==='button');},
    go:async hash=>{location.hash=hash;await win.emit('hashchange');},
    question:async q=>{ids['demander-question'].value=q;await ids['demander-question'].emit('input');},
    submit:()=>ids['demander-form'].emit('submit')};
}
async function pret(options) { const e=environnement(options);await pause();return e; }
function descendants(e) { return [e,...e.children.flatMap(descendants)]; }
const bonneReponse = {reponse:'Une réponse\navec des retours à la ligne.',sources:[]};
(async()=>{
  if(entree.cas==='file') {
    for(const protocol of ['file:','data:','icloud:']) {
      const e=await pret({protocol});assert.equal(e.calls.length,0);
      assert.ok(e.acces.every(a=>a.hidden));assert.ok(e.ids.demander.hidden);
      assert.ok(e.ids['demander-question'].disabled);
    }
  } else if(entree.cas==='decouverte') {
    for(const etat of [null,{}, {disponible:false,jeton:valide.jeton}, {disponible:1,jeton:valide.jeton},
      ...['',null,42,'avec espace','avec\nretour','x'.repeat(513)].map(jeton=>({disponible:true,jeton}))]) {
      const e=await pret({etat});assert.equal(e.calls.length,1);assert.ok(e.acces.every(a=>a.hidden));
      assert.ok(e.ids.demander.hidden);assert.ok(e.ids['demander-question'].disabled);
    }
    const absent=await pret({discoveryStatus:503});assert.ok(absent.ids.demander.hidden);
    for(const protocol of ['http:','https:']) {
      const e=await pret({protocol});assert.ok(e.acces.every(a=>!a.hidden));assert.equal(e.ids.demander.hidden,false);
      assert.ok(e.ids['demander-titre'].focused);assert.equal(e.nav[1].attrs['aria-current'],'page');
      assert.equal(e.calls[0].url,'/api/bobine');assert.equal(e.calls[0].options.method,'GET');
      for(const c of e.calls) {
        assert.equal(c.options.credentials,'same-origin');assert.equal(c.options.mode,'same-origin');
        assert.equal(c.options.cache,'no-store');assert.equal(c.options.redirect,'error');
      }
    }
  } else if(entree.cas==='conversation') {
    const e=await pret({hash:'#bibliotheque'}), d=e.ids;
    assert.ok(d.demander.hidden);
    await e.action.emit('click');await e.go('#demander');
    assert.equal(d['demander-selection'].textContent,e.fiche.titre);assert.equal(d['demander-global'].hidden,false);
    assert.ok(d['demander-aide-selection'].textContent.includes('uniquement à partir de cette vidéo'));
    await e.exemple.emit('click');assert.equal(e.calls.length,1);assert.equal(d['demander-question'].value,e.exemple.dataset.question);
    await e.question('Ma question\n<script>alert(1)</script>');
    const attente={pending:true};e.queue.push(attente);const demande=e.submit();
    assert.ok(d['demander-envoyer'].disabled);assert.ok(d['demander-nouveau'].disabled);assert.ok(d['demander-question'].readOnly);
    assert.equal(d['demander-form'].attrs['aria-busy'],'true');
    await e.submit();await d['demander-question'].emit('keydown',{key:'Enter',ctrlKey:true});
    assert.equal(e.calls.length,2,'Pas de double envoi');
    const corps=JSON.parse(e.calls[1].options.body);assert.equal(corps.fiche,e.fiche.id);assert.deepEqual(corps.historique,[]);
    assert.equal(e.calls[1].options.headers['X-Bobine-Token'],valide.jeton);
    const texte='<img src=x onerror=alert(1)>\n**pas de Markdown**';
    attente.resolve({reponse:texte,sources:[
      {id:e.fiche.id,ancre:'#'+e.fiche.id,titre:'<script>source</script>',lien:'javascript:alert(1)'},
      {id:'f-nouvelle',ancre:'#f-nouvelle',titre:'Nouvelle fiche du serveur',lien:'https://adresse-modele.test/'},
      {id:e.fiche.id,ancre:'#profil',titre:'Profil'},
      {id:e.fiche.id,ancre:'#f-yt_test01%22',titre:'Encodée'},
      {id:e.fiche.id,ancre:'https://exemple.test/',titre:'Externe'},
      {id:e.fiche.id,ancre:'#'+e.fiche.id,titre:'Doublon'},null
    ]});await demande;
    assert.equal(d['demander-question'].value,'');assert.equal(d['demander-messages'].children.length,2);
    const noeuds=descendants(d['demander-messages']);
    assert.ok(noeuds.some(n=>n.textContent===texte));assert.equal(noeuds.filter(n=>n.tagName==='a').length,2);
    assert.equal(noeuds.find(n=>n.tagName==='a').attrs.href,'#'+e.fiche.id);
    assert.equal(noeuds.find(n=>n.tagName==='a').textContent,'<script>source</script>');
    const nouvelle=noeuds.filter(n=>n.tagName==='a')[1];
    assert.equal(nouvelle.textContent,'Nouvelle fiche du serveur');assert.equal(nouvelle.attrs.href,'vault.html#f-nouvelle');
    assert.equal(nouvelle.attrs.target,'_blank');assert.equal(nouvelle.attrs.rel,'noopener noreferrer');
    assert.ok(noeuds.some(n=>n.textContent.includes('bibliothèque a été actualisée')));
    assert.ok(noeuds.every(n=>!['img','script'].includes(n.tagName)));
    await e.question('Mon brouillon');await e.go('#bibliotheque');await e.go('#profil');await e.go('#demander');
    assert.equal(d['demander-question'].value,'Mon brouillon');assert.equal(d['demander-messages'].children.length,2);
    assert.equal(d['demander-selection'].textContent,e.fiche.titre);
    for(let i=0;i<5;i++) {
      await e.question('q'.repeat(2000));e.queue.push({json:{reponse:'r'.repeat(6000),sources:[]}});await e.submit();
      const body=JSON.parse(e.calls.at(-1).options.body);assert.ok(body.historique.length<=6);
      assert.ok(body.historique.every(m=>m.content.length<=800 && ['user','assistant'].includes(m.role)));
    }
    assert.equal(JSON.parse(e.calls.at(-1).options.body).historique.length,6);
    assert.equal(d['demander-messages'].children.length,6);
    const n=e.calls.length;await e.question('x'.repeat(2001));await e.submit();assert.equal(e.calls.length,n);
    await e.question('  ');await e.submit();assert.equal(e.calls.length,n);
    await e.question('Brouillon à garder');await d['demander-global'].emit('click');
    assert.equal(d['demander-question'].value,'Brouillon à garder');assert.equal(d['demander-selection'].textContent,'Toute la bibliothèque');
    assert.equal(d['demander-aide-selection'].textContent,'Bobine cherche dans toute ta bibliothèque.');
    e.queue.push({json:bonneReponse});await e.submit();
    const global=JSON.parse(e.calls.at(-1).options.body);assert.ok(!('fiche' in global));assert.deepEqual(global.historique,[]);
    await d['demander-nouveau'].emit('click');assert.equal(d['demander-question'].value,'');
    assert.equal(d['demander-messages'].children.length,0);assert.equal(e.timers.size,0);
  } else if(entree.cas==='sources_nouvelles') {
    const e=await pret();await e.question('Que retenir ?');
    e.queue.push({json:{reponse:'Réponse sourcée',sources:[
      {id:'f-new_123-A',ancre:'#f-new_123-A',titre:'<img onerror=x> Nouveau titre',href:'javascript:alert(1)',lien:'https://malveillant.test/'},
      {id:'f-new_123-A',ancre:'#f-new_123-A',titre:'Doublon'},
      {id:'f-sans_titre',ancre:'#f-sans_titre',titre:null},
      {id:e.fiche.id,ancre:'#'+e.fiche.id,titre:''},
      ...['f-new\n','f-new\r','f-a b','f-a%22','f-a/../../profil','f-a?x=1','f-a#profil','f-','f-<img>','profil'].map(id=>({id,ancre:'#'+id,titre:'Refusé'})),
      {id:'f-new',ancre:'#f-other',titre:'Refusé'},
      {id:'f-new',ancre:'//exemple.test/#f-new',titre:'Refusé'},
      {id:'f-new',ancre:'javascript:alert(1)',titre:'Refusé'},
      {id:1,ancre:'#f-new',titre:'Refusé'},null
    ]}});await e.submit();
    const noeuds=descendants(e.ids['demander-messages']), liens=noeuds.filter(n=>n.tagName==='a');
    assert.equal(liens.length,3);assert.ok(noeuds.every(n=>n.textContent!=='Refusé'));
    assert.equal(liens[0].attrs.href,'vault.html#f-new_123-A');assert.equal(liens[0].textContent,'<img onerror=x> Nouveau titre');
    assert.equal(liens[1].attrs.href,'vault.html#f-sans_titre');assert.equal(liens[1].textContent,'Fiche source');
    for(const lien of liens.slice(0,2)) {
      assert.equal(lien.attrs.target,'_blank');assert.equal(lien.attrs.rel,'noopener noreferrer');
    }
    assert.equal(liens[2].attrs.href,'#'+e.fiche.id);assert.equal(liens[2].textContent,e.fiche.titre);
    assert.equal(liens[2].attrs.target,undefined);
    assert.equal(noeuds.filter(n=>n.textContent.includes('bibliothèque a été actualisée')).length,1);
    assert.ok(noeuds.every(n=>!['img','script'].includes(n.tagName)));assert.equal(e.calls.length,2);
  } else if(entree.cas==='exemples') {
    const e=await pret({themes:['fidélisation',' fidélisation ','','e-mail','organisation','productivité']}),d=e.ids;
    let boutons=d['demander-exemples'].children;
    assert.equal(boutons.length,3);
    assert.deepEqual(boutons.map(b=>b.textContent),[
      'Que retenir sur « fidélisation » dans mes vidéos ?',
      'Que retenir sur « e-mail » dans mes vidéos ?',
      'Que retenir sur « organisation » dans mes vidéos ?']);
    for(const b of boutons) {
      assert.equal(b.tagName,'button');assert.equal(b.attrs.type,'button');
      await b.emit('click');assert.equal(d['demander-question'].value,b.textContent);
      assert.equal(e.calls.length,1);assert.equal(d['demander-messages'].children.length,0);
    }
    await e.action.emit('click');boutons=d['demander-exemples'].children;
    assert.equal(boutons.length,1);assert.equal(boutons[0].textContent,'Que retenir sur « e-mail » dans cette vidéo ?');
    await boutons[0].emit('click');assert.equal(e.calls.length,1);
    const attente={pending:true};e.queue.push(attente);const demande=e.submit();
    assert.ok(boutons[0].disabled);await boutons[0].emit('click');assert.equal(e.calls.length,2);
    attente.resolve(bonneReponse);await demande;
    await d['demander-global'].emit('click');assert.equal(d['demander-exemples'].children.length,3);
    const piege='<img src=x onerror=alert(1)> — & thème';
    const dangereux=await pret({themes:[piege]});await dangereux.exemple.emit('click');
    assert.ok(dangereux.ids['demander-question'].value.includes(piege));assert.equal(dangereux.exemple.children.length,0);
    const sansThemes=await pret({themes:[],themesFiche:[]});
    assert.ok(sansThemes.exemple.textContent.includes(sansThemes.fiche.titre));
    await sansThemes.action.emit('click');assert.ok(sansThemes.exemple.textContent.includes('cette vidéo'));
    const vide=await pret({themes:[],avecFiche:false});
    assert.equal(vide.exemple,undefined);assert.equal(vide.ids['demander-exemples'].children[0].textContent,'Ouvre une fiche pour poser une question');
    assert.equal(vide.calls.length,1);
  } else if(entree.cas==='exemples_vault') {
    const e=await pret({themes:entree.themes});
    const questions=e.ids['demander-exemples'].children.map(b=>b.dataset.question);
    assert.ok(questions.length);assert.ok(questions.every(q=>entree.themes.some(t=>q.includes('« '+t+' »'))));
    process.stdout.write(JSON.stringify(questions));
  } else if(entree.cas==='erreurs') {
    for(const status of [400,401,403,409,429,502,503,504]) {
      const e=await pret(),d=e.ids;await e.question('Ne pas perdre cette question');
      e.queue.push({status,json:{erreur:'<img src=x>',code:'erreur'}});await e.submit();
      assert.equal(e.calls.length,2);assert.equal(d['demander-question'].value,'Ne pas perdre cette question');
      assert.equal(d['demander-messages'].children.length,0);assert.ok(d['demander-statut'].textContent.includes('conservée'));
      assert.ok(!d['demander-statut'].textContent.includes('<img'));assert.equal(d['demander-form'].attrs['aria-busy'],'false');
      if([401,403,503].includes(status)) {
        assert.ok(d['demander-envoyer'].disabled);assert.equal(d['demander-reconnecter'].hidden,false);
        e.queue.push({json:{disponible:true,jeton:'nouveau-jeton-12345'}});await d['demander-reconnecter'].emit('click');
        assert.equal(e.calls.length,3);assert.equal(e.calls[2].url,'/api/bobine');assert.equal(d['demander-envoyer'].disabled,false);
      }
      e.queue.push({json:bonneReponse});await e.submit();assert.equal(d['demander-messages'].children.length,2);
      assert.deepEqual(JSON.parse(e.calls.at(-1).options.body).historique,[]);
    }
    for(const reponse of [{error:new TypeError('offline')},{json:{}},{json:bonneReponse,contentType:'text/html'}]) {
      const e=await pret();await e.question('Brouillon');e.queue.push(reponse);await e.submit();
      assert.equal(e.ids['demander-question'].value,'Brouillon');assert.ok(e.ids['demander-envoyer'].disabled);
      e.queue.push({json:{disponible:false}});await e.ids['demander-reconnecter'].emit('click');
      assert.equal(e.ids['demander-question'].value,'Brouillon');assert.ok(e.ids['demander-envoyer'].disabled);
      assert.equal(e.calls.filter(c=>c.url==='/api/demander').length,1);
    }
  } else if(entree.cas==='erreurs_precises') {
    const cas=[
      [{status:429,json:{code:'limite',erreur:'La limite quotidienne est atteinte. Réessaie demain.'},retryAfter:'86400'},'Réessaie demain'],
      [{status:429,json:{code:'limite',erreur:'La limite quotidienne est atteinte. Réessaie demain.'},retryAfter:'120'},'Réessaie demain'],
      [{status:429,json:{code:'limite',erreur:'La limite quotidienne est atteinte. Réessaie demain.'}},'Réessaie demain'],
      [{status:429,json:{code:'limite',erreur:'Tu as posé plusieurs questions rapidement.'},retryAfter:'60'},'Patiente une minute'],
      [{status:429,json:{code:'limite',erreur:'Patiente.'},retryAfter:'125'},'Patiente 3 minutes'],
      [{status:429,json:{code:'limite'},retryAfter:'7200'},'Patiente 2 heures'],
      [{status:429,json:{code:'limite'},retryAfter:new Date(Date.now()+90000).toUTCString()},'Patiente 2 minutes'],
      [{status:502,json:{code:'cle_refusee',erreur:'traceback-secret /srv/cle.env'}},'Vérifie la clé dans les réglages'],
      [{status:503,json:{code:'compteur_indisponible',erreur:'traceback-secret PermissionError /vault'}},'Fais vérifier le compteur'],
      [{status:502,json:{code:'configuration_invalide',erreur:'traceback-secret model_not_found'}},'réglages du service'],
      [{status:502,json:{code:'cle_absente',erreur:'traceback-secret'}},'Ajoute une clé'],
      [{status:400,json:{code:'fiche_introuvable',erreur:'traceback-secret'}},'bibliothèque actualisée'],
      [{status:502,json:{code:'reponse_non_verifiable',erreur:'traceback-secret'}},'vérifier les sources'],
      [{status:502,json:{code:'inconnu',erreur:'traceback-secret'}},'Le service d’IA n’a pas pu répondre'],
      [{status:502,json:{code:'constructor',erreur:'traceback-secret'}},'Le service d’IA n’a pas pu répondre'],
      [{status:502,json:{code:'__proto__',erreur:'traceback-secret'}},'Le service d’IA n’a pas pu répondre'],
      [{status:429,jsonError:true,retryAfter:'86400'},'Réessaie demain'],
      [{status:429,contentType:'text/html',json:{code:'limite',erreur:'traceback-secret'},retryAfter:'60'},'Patiente une minute'],
      ...['-1','0','NaN','Infinity','1.5','1e4','999999999','86401','', 'demain','<img>',new Date(0).toUTCString()].map(retryAfter=>[
        {status:429,json:{code:'limite',erreur:'traceback-secret'},retryAfter},'Patiente une minute'])
    ];
    for(const [reponse,attendu] of cas) {
      const e=await pret();await e.question('Question à conserver');e.queue.push(reponse);await e.submit();
      const statut=e.ids['demander-statut'].textContent;
      assert.ok(statut.includes(attendu),statut+' / '+attendu);
      assert.ok(statut.includes('Ta question est conservée. Aucun nouvel envoi automatique.'));
      assert.ok(!/traceback-secret|PermissionError|<img>|—|undefined|NaN|Infinity/.test(statut),statut);
      assert.equal(e.ids['demander-question'].value,'Question à conserver');assert.equal(e.ids['demander-messages'].children.length,0);
      assert.equal(e.ids['demander-statut'].children.length,0);assert.equal(e.calls.length,2);assert.equal(e.timers.size,0);
    }
  } else if(entree.cas==='expiration') {
    const e=await pret();await e.question('Question conservée après délai');
    const attente={pending:true};e.queue.push(attente);const demande=e.submit();
    assert.equal(e.timers.size,1);[...e.timers.values()][0]();await demande;
    assert.equal(e.ids['demander-question'].value,'Question conservée après délai');
    assert.ok(e.ids['demander-statut'].textContent.includes('trop de temps'));
    assert.equal(e.calls.length,2);assert.equal(e.timers.size,0);
  } else { throw new Error('Cas inconnu'); }
})().catch(e=>{console.error(e);process.exitCode=1;});
"""


@unittest.skipUnless(shutil.which("node"), "Node facultatif pour les tests JS sans réseau")
class DemanderJavascript(unittest.TestCase):
    def verifier(self, cas, **donnees):
        resultat = subprocess.run([shutil.which("node"), "-e", HARNAIS_DEMANDER],
                                  input=json.dumps({"js": script_demander(generate_page.TEMPLATE_LISTE), "cas": cas, **donnees}),
                                  text=True, capture_output=True, timeout=20)
        self.assertEqual(resultat.returncode, 0, resultat.stdout + resultat.stderr)
        return resultat.stdout

    def test_file_ne_declenche_aucun_fetch(self):
        self.verifier("file")

    def test_decouverte_jeton_deep_link_et_repli(self):
        self.verifier("decouverte")

    def test_conversation_sources_echappement_historique_navigation_et_double_envoi(self):
        self.verifier("conversation")

    def test_erreurs_question_preservee_et_reconnexion_sans_renvoi(self):
        self.verifier("erreurs")

    def test_sources_nouvelles_sures_et_page_actualisee(self):
        self.verifier("sources_nouvelles")

    def test_erreurs_precises_et_retry_after_borne(self):
        self.verifier("erreurs_precises")

    def test_exemples_themes_selection_fiches_et_bibliotheque_vide(self):
        self.verifier("exemples")

    def test_exemples_du_vault_trouvent_des_fiches_sans_appel_externe(self):
        import demander
        with tempfile.TemporaryDirectory() as dossier:
            racine = vault_demo(dossier)
            balises = BalisesPage(generer(racine)).balises
            themes = [a["data-t"] for _, a in balises if a.get("data-t")]
            questions = json.loads(self.verifier("exemples_vault", themes=themes))
            ids = [a["id"] for tag, a in balises if tag == "article" and a.get("class") == "fiche"]
            for question in questions:
                with self.subTest(question=question), \
                        mock.patch.object(demander.enrichir, "charger_config", return_value={}), \
                        mock.patch.object(demander.enrichir, "resoudre_fournisseur",
                                          return_value=("cle-factice", "https://service.test", "modele-factice")), \
                        mock.patch.object(demander, "_appeler", return_value={
                            "reponse": "Réponse de test.", "sources": ids}) as appeler:
                    resultat = demander.repondre(racine, question)
                    self.assertTrue(resultat["sources"])
                    appeler.assert_called_once()

    def test_delai_sans_nouvel_envoi(self):
        self.verifier("expiration")


if __name__ == "__main__":
    unittest.main()
