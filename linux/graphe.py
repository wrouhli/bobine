#!/usr/bin/env python3
"""
graphe.py - Cree les liens Obsidian a partir de index.md.

Ce script ne fait AUCUN appel a une IA : il lit simplement index.md, retrouve
la fiche correspondante dans raw/, et y ajoute des liens [[Theme]].
Il cree aussi une note par theme dans themes/, ce qui donne les gros noeuds
du graphe.

Relancable sans risque : une fiche deja traitee est laissee telle quelle.

Usage :
    python graphe.py --vault "~/Bobine"
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

MARQUEUR = "## Liens"


def identifiant(lien):
    """Meme logique que ingest.py : derive le nom de fichier depuis l'URL."""
    # Couper la query AVANT de prendre le dernier segment (liens partages par
    # l'appli instagram : ".../reel/ABC/?stkn=..." sinon nom vide).
    fin = lien.split("?")[0].rstrip("/").split("/")[-1]
    fin = re.sub(r"[^A-Za-z0-9_-]", "", fin)[:40]
    plateforme = "tiktok" if "tiktok" in lien else "insta"
    return f"{plateforme}_{fin}"


def nom_sur(texte):
    """Un nom de note sans caractere interdit (/, :, etc.)."""
    return re.sub(r'[\\/:*?"<>|\[\]#^]', "", texte).strip()


def lire_index(chemin):
    """Decoupe index.md en entrees {titre, lien, themes}."""
    texte = chemin.read_text(encoding="utf-8", errors="ignore")
    entrees = []

    for bloc in re.split(r"\n(?=###\s)", texte):
        if not bloc.lstrip().startswith("###"):
            continue

        titre = bloc.lstrip()[3:].split("\n")[0].strip()

        m_lien = re.search(r"^[-*]\s*lien\s*:\s*(\S+)", bloc, re.M | re.I)
        m_themes = re.search(r"^[-*]\s*th[eè]mes?\s*:\s*(.+)$", bloc, re.M | re.I)
        if not m_lien:
            continue

        themes = []
        if m_themes:
            themes = [
                nom_sur(t) for t in m_themes.group(1).split(",") if nom_sur(t)
            ]

        entrees.append({
            "titre": titre,
            "lien": m_lien.group(1).rstrip(".,);"),
            "themes": themes,
        })

    return entrees


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--vault", required=True)
    args = p.parse_args()

    vault = Path(args.vault)
    index = vault / "index.md"
    dossier_raw = vault / "raw"
    dossier_themes = vault / "themes"

    if not index.exists():
        print(f"index.md introuvable dans {vault}")
        return
    if not dossier_raw.exists():
        print(f"dossier raw introuvable dans {vault}")
        return

    dossier_themes.mkdir(exist_ok=True)
    entrees = lire_index(index)
    print(f"{len(entrees)} entrees lues dans index.md\n")

    par_theme = defaultdict(list)
    modifiees = deja = introuvables = 0

    for e in entrees:
        for t in e["themes"]:
            par_theme[t].append(e)

        fiche = dossier_raw / f"{identifiant(e['lien'])}.md"
        if not fiche.exists():
            introuvables += 1
            continue

        contenu = fiche.read_text(encoding="utf-8", errors="ignore")
        if MARQUEUR in contenu:
            deja += 1
            continue

        liens = " ".join(f"[[{t}]]" for t in e["themes"]) or "(aucun theme)"
        fiche.write_text(
            f"{contenu.rstrip()}\n\n{MARQUEUR}\n{liens}\n",
            encoding="utf-8",
        )
        modifiees += 1

    # une note par theme : c'est elle qui devient un gros noeud du graphe
    for theme, liste in sorted(par_theme.items()):
        lignes = [f"# {theme}", "", f"{len(liste)} fiches.", ""]
        for e in sorted(liste, key=lambda x: x["titre"].lower()):
            note = identifiant(e["lien"])
            lignes.append(f"- [[{note}|{e['titre']}]]")
        (dossier_themes / f"{theme}.md").write_text(
            "\n".join(lignes) + "\n", encoding="utf-8"
        )

    print(f"fiches enrichies   : {modifiees}")
    print(f"deja faites        : {deja}")
    print(f"fiches introuvables: {introuvables}")
    print(f"notes de theme     : {len(par_theme)} dans {dossier_themes}")
    print("\nOuvre Obsidian, puis la vue graphe (icone cercles a gauche).")


if __name__ == "__main__":
    main()
