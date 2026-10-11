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
        # Dernier segment entièrement nettoyé → repli sur une courte empreinte.
        nom = ingest.identifiant("https://www.tiktok.com/@u/video/...")
        self.assertRegex(nom, r"^tiktok_[0-9a-f]{10}$")

    def test_repli_stable_d_un_lancement_a_l_autre(self):
        # hash() de Python change à chaque lancement : le repli doit être stable.
        import subprocess
        code = ("import sys; sys.path.insert(0, %r); import ingest; "
                "print(ingest.identifiant('https://www.instagram.com/reel/\u2713\u2713/'))"
                % str(Path(ingest.__file__).resolve().parent))
        noms = {subprocess.run([sys.executable, "-c", code], capture_output=True,
                               text=True).stdout.strip() for _ in range(3)}
        self.assertEqual(len(noms), 1)
        self.assertRegex(noms.pop(), r"^insta_[0-9a-f]{10}$")


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


class Pluriel(unittest.TestCase):
    """pluriel : singulier pour 0 et 1, pluriel à partir de 2."""

    def test_singulier_pour_zero_et_un(self):
        self.assertEqual(ingest.pluriel(0, "échec"), "0 échec")
        self.assertEqual(ingest.pluriel(1, "fiche"), "1 fiche")
        self.assertEqual(ingest.pluriel(1, "réussite"), "1 réussite")

    def test_pluriel_a_partir_de_deux(self):
        self.assertEqual(ingest.pluriel(2, "fiche"), "2 fiches")
        self.assertEqual(ingest.pluriel(3, "lien"), "3 liens")
        self.assertEqual(ingest.pluriel(12, "thème"), "12 thèmes")


if __name__ == "__main__":
    unittest.main()


class LienCanonique(unittest.TestCase):
    """lien_canonique : une même vidéo, quels que soient les paramètres de suivi."""

    def test_youtube_toutes_les_formes(self):
        attendu = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        for lien in ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=AAA",
                     "https://youtu.be/dQw4w9WgXcQ?si=BBB",
                     "https://m.youtube.com/shorts/dQw4w9WgXcQ?feature=share",
                     "https://www.youtube.com/live/dQw4w9WgXcQ"):
            self.assertEqual(ingest.lien_canonique(lien), attendu)

    def test_instagram_et_tiktok_sans_parametres(self):
        self.assertEqual(
            ingest.lien_canonique("https://www.instagram.com/reel/ABC123/?igsh=xyz"),
            "https://www.instagram.com/reel/ABC123/")
        self.assertEqual(
            ingest.lien_canonique("https://www.instagram.com/reel/ABC123"),
            "https://www.instagram.com/reel/ABC123/")
        self.assertEqual(
            ingest.lien_canonique("https://www.tiktok.com/@u/video/7300000000000000001?_r=1"),
            "https://www.tiktok.com/@u/video/7300000000000000001")

    def test_vide(self):
        self.assertEqual(ingest.lien_canonique(""), "")
        self.assertEqual(ingest.lien_canonique(None), "")

    def test_extraire_liens_dedoublonne_par_forme_canonique(self):
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "liens.txt"
            fichier.write_text(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=A\n"
                "https://youtu.be/dQw4w9WgXcQ?si=B\n"
                "https://www.instagram.com/reel/ABC123/?igsh=1\n"
                "https://www.instagram.com/reel/ABC123/?igsh=2\n",
                encoding="utf-8")
            self.assertEqual(len(ingest.extraire_liens(fichier)), 2)


class Journal(unittest.TestCase):
    """journal.json : clés canoniques, reprise d'un journal abîmé."""

    def test_normaliser_fusionne_et_prefere_ok(self):
        journal = {
            "https://youtu.be/dQw4w9WgXcQ?si=A": {"statut": "echec", "tentatives": 1},
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=B": {"statut": "ok", "fiche": "yt.md"},
        }
        propre = ingest.normaliser_journal(journal)
        self.assertEqual(list(propre), ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
        self.assertEqual(propre["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]["statut"], "ok")
        self.assertEqual(
            ingest.entree_journal(propre, "https://youtu.be/dQw4w9WgXcQ?si=Z")["statut"], "ok")

    def test_journal_abime_est_reconstruit_depuis_raw(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            (racine / "raw").mkdir()
            (racine / "raw" / "insta_ABC.md").write_text(
                "---\nsource: https://www.instagram.com/reel/ABC/\n---\n# t\n",
                encoding="utf-8")
            (racine / "journal.json").write_text('{"https://x": {"statut": "ok"',
                                                 encoding="utf-8")
            journal = ingest.charger_journal(racine / "journal.json")
            restes = sorted(p.name for p in racine.iterdir())
        self.assertEqual(journal["https://www.instagram.com/reel/ABC/"]["statut"], "ok")
        self.assertTrue(any(n.startswith("journal.json.abime-") for n in restes))
        self.assertNotIn("journal.json", restes)

    def test_ecriture_atomique_sans_reste(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "journal.json"
            ingest.sauver_journal(chemin, {"a": {"statut": "ok"}})
            self.assertEqual(sorted(p.name for p in Path(dossier).iterdir()), ["journal.json"])
            self.assertIn('"statut": "ok"', chemin.read_text(encoding="utf-8"))


class Fiche(unittest.TestCase):
    """ecrire_fiche : l'en-tête ne peut pas être cassé par la plateforme."""

    def test_auteur_et_titre_sur_une_ligne(self):
        with tempfile.TemporaryDirectory() as dossier:
            meta = {"uploader": "Auteur\nstatut: faux", "title": "Titre\n---\nsource: x",
                    "description": "desc", "duration": 12}
            ingest.ecrire_fiche(Path(dossier), "yt_x", "https://youtu.be/dQw4w9WgXcQ?si=1",
                                meta, "texte", "video", "whisper (local)")
            texte = (Path(dossier) / "yt_x.md").read_text(encoding="utf-8")
        entete = texte.split("---\n")[1]
        self.assertIn("auteur: Auteur statut: faux\n", entete)
        self.assertEqual(sum(1 for l in entete.splitlines() if l.startswith("statut:")), 1)
        self.assertIn("source: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n", entete)
        self.assertIn("# Titre --- source: x\n", texte)

    def test_nettoyer_temporaires(self):
        with tempfile.TemporaryDirectory() as dossier:
            d = Path(dossier)
            for nom in ("yt_x.m4a", "yt_x.webm.part", "subs_yt_x.fr.vtt", "yt_y.m4a"):
                (d / nom).write_text("x", encoding="utf-8")
            ingest.nettoyer_temporaires(d, "yt_x")
            self.assertEqual(sorted(p.name for p in d.iterdir()), ["yt_y.m4a"])
