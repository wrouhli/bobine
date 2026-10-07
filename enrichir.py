#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bobine — enrichir.py

Résume les nouvelles fiches de raw/ et met à jour index.md.

Pour chaque fiche qui n'est pas encore dans l'index, ce script demande à un
modèle (via une API compatible OpenAI : DeepSeek, OpenAI, OpenRouter…) un
titre, des thèmes et un résumé concret, puis les ajoute à index.md et
régénère les pages (vault.html / graph.html).

Sans clé API configurée (voir config.example.env), l'étape est simplement
sautée : la transcription et tout le reste fonctionnent sans.

Usage :
  python enrichir.py                 # traite les nouvelles fiches du dossier courant
  python enrichir.py --dry-run       # montre ce qui serait fait (aucun appel, aucune écriture)
  python enrichir.py --limite 10     # plafonne le nombre de fiches traitées
  python enrichir.py --no-pages      # ne pas régénérer les pages HTML à la fin
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ------------------------------------------------------------------ réglages

# Services compatibles OpenAI : (adresse par défaut, modèle par défaut)
FOURNISSEURS = {
    "DEEPSEEK_API_KEY":   ("https://api.deepseek.com/v1", "deepseek-chat"),
    "OPENAI_API_KEY":     ("https://api.openai.com/v1", None),
    "OPENROUTER_API_KEY": ("https://openrouter.ai/api/v1", None),
    "GEMINI_API_KEY":     ("https://generativelanguage.googleapis.com/v1beta/openai", None),
}

ENTETE_INDEX = """# Index du Vault

Ce fichier est la version « condensée » des fiches de raw/ : une entrée par vidéo,
avec un résumé concret et des thèmes. La page vault.html est générée à partir d'ici.

"""

CONSIGNE = """Tu ranges des fiches de veille dans un index.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, au format :
{"titre": "...", "themes": ["..."], "contenu": "..."}

Règles :
- "titre" : court (80 caractères maximum), concret, en français.
- "themes" : 2 à 4 thèmes courts en minuscules (exemples : "ia", "open source", "seo").
- "contenu" : 3 à 5 phrases en français. Garde les noms d'outils, les chiffres et les idées concrètes ; pas de blabla.
- Si la fiche ne contient pas d'information utile (vidéo sans parole), dis-le sobrement dans "contenu"."""


# ------------------------------------------------------------------ outils

def charger_config(*dossiers):
    """Lit les fichiers config.env (format clé=valeur, # commentaires)."""
    cfg = {}
    for dossier in dossiers:
        fichier = Path(dossier) / "config.env"
        if not fichier.is_file():
            continue
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, valeur = ligne.split("=", 1)
            valeur = valeur.strip().strip('"').strip("'")
            if valeur:
                cfg[cle.strip()] = valeur
    return cfg


def resoudre_fournisseur(cfg):
    """Retourne (clé API, adresse, modèle) d'après la config, ou (None, None, None)."""
    cle = cfg.get("API_KEY") or os.environ.get("API_KEY")
    adresse = cfg.get("API_BASE_URL") or os.environ.get("API_BASE_URL")
    modele = cfg.get("API_MODEL") or os.environ.get("API_MODEL")
    if cle and adresse:
        return cle, adresse, modele
    for nom_variable, (adresse_defaut, modele_defaut) in FOURNISSEURS.items():
        cle = cfg.get(nom_variable) or os.environ.get(nom_variable)
        if cle:
            return cle, adresse or adresse_defaut, modele or modele_defaut
    return None, None, None


def code_court(url):
    """Extrait l'identifiant d'un lien Instagram (reel, reels, p, tv)."""
    m = re.search(r"instagram\.com/(?:reel|reels|p|tv)/([^/?#\s]+)", url or "")
    return m.group(1) if m else None


def lire_fiche(chemin):
    """Retourne (texte complet, champs du bloc --- d'en-tête)."""
    texte = chemin.read_text(encoding="utf-8", errors="ignore")
    champs = {}
    m = re.match(r"^---\n(.*?)\n---\n", texte, re.S)
    if m:
        for ligne in m.group(1).splitlines():
            if ":" in ligne:
                cle, valeur = ligne.split(":", 1)
                champs[cle.strip()] = valeur.strip()
    return texte, champs


def liens_deja_indexes(chemin_index):
    """Retourne (codes courts, URL complètes) déjà présents dans index.md."""
    codes, urls = set(), set()
    if chemin_index.is_file():
        for ligne in chemin_index.read_text(encoding="utf-8").splitlines():
            if ligne.strip().startswith("- lien :"):
                url = ligne.split("- lien :", 1)[1].strip()
                urls.add(url)
                code = code_court(url)
                if code:
                    codes.add(code)
    return codes, urls


def ajouter_entree(chemin_index, entree):
    """Ajoute une entrée à la fin de index.md (crée le fichier au besoin)."""
    base = chemin_index.read_text(encoding="utf-8") if chemin_index.is_file() else ENTETE_INDEX
    if not base.endswith("\n"):
        base += "\n"
    base += "\n" + entree.rstrip() + "\n"
    chemin_index.write_text(base, encoding="utf-8")


# ------------------------------------------------------------------ modèle

def demander_resume(cle, adresse, modele, texte_fiche):
    """Interroge le modèle et retourne le dict {titre, themes, contenu}, ou None."""
    messages = [
        {"role": "system", "content": CONSIGNE},
        {"role": "user", "content": "Fiche à résumer :\n\n" + texte_fiche[:8000]},
    ]
    derniere_erreur = None
    for tentative in (1, 2):  # une seule relance : les réponses JSON ratées sont rares
        try:
            corps = json.dumps({
                "model": modele,
                "messages": messages,
                "temperature": 0.3,
            }).encode("utf-8")
            requete = urllib.request.Request(
                adresse.rstrip("/") + "/chat/completions",
                data=corps,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + cle,
                    "User-Agent": "bobine/0.1",
                },
            )
            # Requête volontairement synchrone : le script tourne en tâche de
            # fond, une fiche à la fois — et on garde zéro dépendance à installer.
            with urllib.request.urlopen(requete, timeout=120) as reponse:
                donnees = json.loads(reponse.read().decode("utf-8"))
            contenu = donnees["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", contenu, re.S)
            if not m:
                raise ValueError("réponse sans JSON")
            return json.loads(m.group(0))
        except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError, TimeoutError) as erreur:
            derniere_erreur = erreur
    print("    (" + str(derniere_erreur) + ")")
    return None


# ------------------------------------------------------------------ principal

def main():
    ap = argparse.ArgumentParser(description="Résume les nouvelles fiches et met à jour l'index.")
    ap.add_argument("--vault", default=str(Path(__file__).resolve().parent),
                    help="dossier du Vault (par défaut : le dossier de ce script)")
    ap.add_argument("--limite", type=int, default=0, help="nombre maximum de fiches à traiter (0 = toutes)")
    ap.add_argument("--dry-run", action="store_true", help="montre ce qui serait fait, sans appel ni écriture")
    ap.add_argument("--no-pages", action="store_true", help="ne pas régénérer les pages HTML à la fin")
    args = ap.parse_args()

    racine = Path(args.vault).expanduser().resolve()
    script = Path(__file__).resolve().parent
    chemin_index = racine / "index.md"
    dossier_fiches = racine / "raw"

    if not dossier_fiches.is_dir():
        print("Dossier raw/ introuvable dans " + str(racine) + " — rien à faire.")
        return 0

    cfg = charger_config(script, racine)
    cle, adresse, modele = resoudre_fournisseur(cfg)

    deja_codes, deja_urls = liens_deja_indexes(chemin_index)

    en_attente = []
    for fiche in sorted(dossier_fiches.glob("*.md"), key=lambda p: p.stat().st_mtime):
        if fiche.name.startswith("."):
            continue   # fichiers cachés (.DS_Store, « ._ » AppleDouble…) : jamais des fiches
        _, champs = lire_fiche(fiche)
        source = champs.get("source", "")
        code = code_court(source)
        if (code and code in deja_codes) or (not code and source and source in deja_urls):
            continue
        en_attente.append((fiche, champs))

    if not en_attente:
        print("Index à jour — aucune nouvelle fiche à résumer. ✨")
        return 0

    if args.dry_run:
        print(str(len(en_attente)) + " fiche(s) en attente de résumé :")
        for fiche, champs in en_attente:
            print("  - " + fiche.name + "  (" + champs.get("auteur", "?") + ")")
        fiche, _ = en_attente[0]
        apercu = fiche.read_text(encoding="utf-8", errors="ignore")[:280].replace("\n", " ")
        print("\nAperçu de ce qui serait envoyé (1re fiche) :\n  " + apercu + "…")
        print("\nMode --dry-run : aucun appel API, aucune écriture.")
        return 0

    if not cle:
        print("Aucune clé API configurée (voir config.example.env) — étape résumé sautée.")
        print("(" + str(len(en_attente)) + " fiche(s) attendent un résumé.)")
        return 0
    if not modele:
        print("API_MODEL n'est pas défini pour ce fournisseur — voir config.example.env.")
        return 1

    traitees = 0
    for fiche, champs in en_attente:
        if args.limite and traitees >= args.limite:
            print("Limite de " + str(args.limite) + " atteinte — le reste au prochain passage.")
            break
        texte = fiche.read_text(encoding="utf-8", errors="ignore")
        resultat = demander_resume(cle, adresse, modele, texte)
        if not resultat:
            print("  ✗ " + fiche.name + " : échec du modèle, fiche laissée pour la prochaine fois.")
            continue
        titre = str(resultat.get("titre", "")).strip() or fiche.stem
        themes = resultat.get("themes", [])
        if isinstance(themes, str):
            themes = [t.strip() for t in themes.split(",") if t.strip()]
        themes = [str(t).lower().strip() for t in themes if str(t).strip()]
        resume = str(resultat.get("contenu", "")).strip()
        url = champs.get("source", "")
        auteur = champs.get("auteur", "")
        entree = ("### " + titre + "\n"
                  "- lien : " + url + "\n"
                  "- auteur : " + auteur + "\n"
                  "- thèmes : " + ", ".join(themes) + "\n"
                  "- contenu : " + resume + "\n")
        ajouter_entree(chemin_index, entree)
        traitees += 1
        print("  ✓ " + fiche.name + " → « " + titre + " »")

    if traitees and not args.no_pages:
        page_script = script / "generate_page.py"
        if page_script.is_file():
            print("Régénération des pages…")
            sous = subprocess.run([sys.executable, str(page_script), "--vault", str(racine)])
            if sous.returncode != 0:
                print("(les pages n'ont pas pu être régénérées — relance generate_page.py)")

    print("Terminé — " + str(traitees) + " fiche(s) résumée(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
