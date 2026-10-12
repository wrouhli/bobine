#!/usr/bin/env python3
"""generate_page.py — fabrique vault.html (liste consultable) et graph.html
(la carte du graphe) à partir de index.md. Sur macOS, en dépose aussi une
copie dans iCloud Drive pour l'iPhone ; sous Linux, cette étape est ignorée.

Usage : python3 generate_page.py [--vault ~/Vault]
"""

import argparse
import html
import json
import re
import shlex
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

# Outils partagés avec l'ingestion (même dossier).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest import ecrire_atomique, identifiant, lien_canonique  # noqa: E402
from enrichir import FICHIER_PROFIL, lire_memo, lire_profil  # noqa: E402

VAULT = Path(__file__).resolve().parent
NOM_DEFAUT = "Bobine"


def lire_config(*dossiers):
    """Lit config.env (clé=valeur) dans les dossiers donnés."""
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


def lien_sur(lien):
    """Le lien tel quel s'il pointe vers une page web (http ou https), sinon "".

    Les liens de l'index viennent de la plateforme et du modèle d'IA : un lien
    « javascript: », « data: » ou « file: » ne doit jamais devenir cliquable
    sur la page."""
    lien = (lien or "").strip()
    return lien if re.match(r"(?i)^https?://[^\s\"'<>]+$", lien) else ""


def remplir(modele, valeurs):
    """Remplace les repères (« __CHIPS__ », « __SVG__ »…) en UN seul passage.

    Remplacer repère par repère (str.replace en chaîne) re-parcourt aussi le
    contenu déjà inséré : un titre contenant « __SVG__ » recevait alors tout le
    SVG, et la page se cassait. Ici, le texte inséré n'est jamais relu."""
    if not valeurs:
        return modele
    motif = re.compile("|".join(re.escape(cle) for cle in
                                sorted(valeurs, key=len, reverse=True)))
    return motif.sub(lambda m: valeurs[m.group(0)], modele)


def lire_index(chemin):
    """Lit index.md et retourne une liste d'entrées
    {titre, lien, auteur, themes, contenu}. Fichier absent → liste vide.
    Dans un bloc, la PREMIÈRE ligne de chaque champ fait foi (une ligne en
    double ne peut pas remplacer le vrai lien)."""
    entrees = []
    courant = None
    if not chemin.is_file():
        return entrees
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if ligne.startswith("### "):
            courant = {"titre": ligne[4:].strip(), "lien": "", "auteur": "",
                       "themes": [], "contenu": ""}
            entrees.append(courant)
        elif courant is not None:
            for prefixe, champ in (("- lien :", "lien"),
                                   ("- auteur :", "auteur"),
                                   ("- contenu :", "contenu")):
                if ligne.startswith(prefixe) and not courant[champ]:
                    courant[champ] = ligne[len(prefixe):].strip()
            if ligne.startswith("- thèmes :") and not courant["themes"]:
                courant["themes"] = [t.strip() for t in
                                     ligne[len("- thèmes :"):].split(",")
                                     if t.strip()]
    return [e for e in entrees if e["titre"]]


def pluriel(n, mot):
    """Accord simple : singulier pour 0 et 1 (« 0 échec », « 1 fiche »),
    pluriel à partir de 2 (« 2 fiches »)."""
    return f"{n} {mot}" if n < 2 else f"{n} {mot}s"


def positions_initiales(entrees, iterations=700):
    """Simule la physique du graphe côté Python, pour livrer une carte déjà
    équilibrée : le navigateur (et l'aperçu iPhone) n'a plus qu'à l'afficher.
    Mêmes constantes que la simulation JS de graph.html."""
    import numpy as np  # dispo dans le venv (dépendance de faster-whisper)

    nb_fiches = len(entrees)
    theme_ids = {}
    edges = []
    nb = nb_fiches
    for i, e in enumerate(entrees):
        for t in e["themes"]:
            if t not in theme_ids:
                theme_ids[t] = nb
                nb += 1
            edges.append((i, theme_ids[t]))

    n = nb
    pos = np.zeros((n, 2))
    nt = n - nb_fiches
    for i in range(nb_fiches):
        a = (i / max(1, nb_fiches)) * 2 * np.pi
        pos[i] = (np.cos(a) * 320, np.sin(a) * 320)
    for k in range(nt):
        a = (k / max(1, nt)) * 2 * np.pi
        pos[nb_fiches + k] = (np.cos(a) * 160, np.sin(a) * 160)

    vel = np.zeros((n, 2))
    E = np.array(edges, dtype=int) if edges else np.zeros((0, 2), dtype=int)

    for _ in range(iterations):
        d = pos[:, None, :] - pos[None, :, :]
        d2 = (d ** 2).sum(-1)
        np.fill_diagonal(d2, np.inf)
        d2 = np.maximum(d2, 1.0)
        dist = np.sqrt(d2)
        force = (d / dist[..., None]) * (4200.0 / d2)[..., None]
        net = force.sum(axis=1)
        if len(E):
            dv = pos[E[:, 1]] - pos[E[:, 0]]
            dl = np.maximum(1.0, np.sqrt((dv ** 2).sum(-1)))
            fv = dv / dl[:, None] * ((dl - 115.0) * 0.028)[:, None]
            np.add.at(net, E[:, 0], fv)
            np.add.at(net, E[:, 1], -fv)
        vel += net
        vel += -pos * 0.006
        vel *= 0.84
        pos += vel

    return [[round(float(x), 1), round(float(y), 1)] for x, y in pos]


TEMPLATE_LISTE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vault · mes vidéos sauvegardées</title>
<link rel="icon" href="__FAVICON__">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#FFFFFF">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#000000">
<style>
  /* Identité visuelle : blanc, gris platine, noir ; l'ambre seulement pour
     guider le regard ; le jaune pâle pour les encadrés. Aucune ressource
     externe : la bibliothèque reste lisible hors ligne. Demander ne contacte
     que le serveur de cette page, après découverte explicite de sa disponibilité. */
  :root{
    --fond:#FFFFFF; --surface:#F3F4F6; --surface-survol:#FFFFFF;
    --encre:#000000; --encre-2:rgba(0,0,0,.62); --encre-3:rgba(0,0,0,.45);
    --trait:rgba(0,0,0,.09); --trait-fort:rgba(0,0,0,.16);
    --ambre:#FEC90A; --sur-ambre:#000000; --chiffon:#FFF1C5;
    --actif-fond:#000000; --actif-encre:#FFFFFF;
    --lien:#000000; --verre:rgba(255,255,255,.92); --ombre:0 1px 2px rgba(0,0,0,.08);
  }
  :root[data-theme="dark"]{
    --fond:#000000; --surface:rgba(255,255,255,.07); --surface-survol:rgba(255,255,255,.11);
    --encre:#FFFFFF; --encre-2:rgba(255,255,255,.68); --encre-3:rgba(255,255,255,.48);
    --trait:rgba(255,255,255,.12); --trait-fort:rgba(255,255,255,.22);
    --chiffon:rgba(254,201,10,.16);
    --actif-fond:#FFFFFF; --actif-encre:#000000;
    --lien:#FEC90A; --verre:rgba(0,0,0,.88); --ombre:none;
  }
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      --fond:#000000; --surface:rgba(255,255,255,.07); --surface-survol:rgba(255,255,255,.11);
      --encre:#FFFFFF; --encre-2:rgba(255,255,255,.68); --encre-3:rgba(255,255,255,.48);
      --trait:rgba(255,255,255,.12); --trait-fort:rgba(255,255,255,.22);
      --chiffon:rgba(254,201,10,.16);
      --actif-fond:#FFFFFF; --actif-encre:#000000;
      --lien:#FEC90A; --verre:rgba(0,0,0,.88); --ombre:none;
    }
  }
  *{box-sizing:border-box}
  [hidden]{display:none !important}
  html,body{margin:0}
  html{scroll-behavior:auto}
  body{background:var(--fond);color:var(--encre);
    font:16px/1.55 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Inter,Roboto,Arial,sans-serif;
    -webkit-font-smoothing:antialiased}
  a{color:inherit}
  button{font:inherit;color:inherit}
  ::selection{background:var(--ambre);color:var(--sur-ambre)}
  :focus-visible{outline:2px solid var(--encre);outline-offset:2px;border-radius:6px}
  @media (prefers-reduced-motion: reduce){ *{transition:none !important; animation:none !important} }
  .ico{width:18px;height:18px;flex:none}
  .ico path,.ico circle,.ico rect{fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}

  .enveloppe{max-width:1180px;margin:0 auto;padding:0 28px 72px}
  .tete{position:sticky;top:0;z-index:10;background:var(--verre);
    backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--trait)}
  .tete-in{max-width:1180px;margin:0 auto;padding:14px 28px;display:flex;align-items:center;gap:18px}
  .marque{display:flex;align-items:center;gap:9px;font-weight:700;font-size:18px;letter-spacing:-.01em;text-decoration:none}
  .marque .ico{width:24px;height:24px}
  .droite{margin-left:auto;display:flex;align-items:center;gap:14px}
  .nav{display:flex;gap:4px;margin-left:10px}
  .nav a{font-size:14.5px;font-weight:500;color:var(--encre-2);text-decoration:none;padding:7px 13px;border-radius:999px}
  .nav a:hover{background:var(--surface);color:var(--encre)}
  .nav .nav-biblio{background:var(--actif-fond);color:var(--actif-encre)}
  body:has(#profil:target) .nav .nav-biblio{background:transparent;color:var(--encre-2)}
  body:has(#profil:target) .nav .nav-profil{background:var(--actif-fond);color:var(--actif-encre)}
  .lien-carte-mobile{display:none;margin-top:14px;font-size:14px;font-weight:500;color:var(--encre-2)}
  .lien-carte{font-size:14px;font-weight:500;color:var(--encre-2);text-decoration:none;padding:7px 12px;border-radius:999px}
  .lien-carte:hover{background:var(--surface);color:var(--encre)}
  .theme{display:flex;gap:2px;background:var(--surface);border-radius:999px;padding:3px}
  .tbtn{width:30px;height:26px;display:grid;place-items:center;border:0;background:transparent;
    border-radius:999px;color:var(--encre-3);cursor:pointer;padding:0}
  .tbtn:hover{color:var(--encre)}
  .tbtn.on{background:var(--fond);color:var(--encre);box-shadow:var(--ombre)}

  /* ---------- bibliothèque ---------- */
  #bibliotheque{padding-top:34px}
  .titre{font-size:32px;font-weight:700;letter-spacing:-.02em;line-height:1.15;margin:0}
  .sous{color:var(--encre-2);margin:6px 0 0}
  .recherche{margin-top:24px;display:flex;align-items:center;gap:12px;background:var(--surface);
    border:2px solid transparent;border-radius:14px;padding:13px 16px;transition:border-color .15s}
  .recherche:focus-within{border-color:var(--ambre);background:var(--fond)}
  .recherche input{border:0;outline:0;background:transparent;flex:1;font:inherit;font-size:17px;color:var(--encre);min-width:0}
  .recherche input::placeholder{color:var(--encre-3)}
  .recherche .ico{color:var(--encre-3)}
  .chips{display:flex;gap:8px;margin-top:18px;overflow-x:auto;padding-bottom:4px;scrollbar-width:none}
  .chips::-webkit-scrollbar{display:none}
  .chip{flex:none;padding:7px 14px;border-radius:999px;border:1px solid var(--trait-fort);background:transparent;
    font-size:14px;font-weight:500;color:var(--encre-2);cursor:pointer}
  .chip .n{opacity:.55;margin-left:3px;font-size:.88em}
  .chip:hover{color:var(--encre)}
  .chip.on{background:var(--actif-fond);border-color:var(--actif-fond);color:var(--actif-encre)}
  .grille{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:14px;margin-top:8px}
  .mois{grid-column:1/-1;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;
    color:var(--encre-3);margin:26px 0 2px}
  .carte{display:flex;flex-direction:column;gap:9px;text-decoration:none;background:var(--surface);
    border:1px solid transparent;border-radius:14px;padding:18px 20px;transition:background .15s,border-color .15s}
  .carte:hover{background:var(--surface-survol);border-color:var(--trait-fort)}
  .carte h2{font-size:17px;font-weight:600;line-height:1.35;letter-spacing:-.01em;margin:0}
  .res{margin:0;font-size:14.5px;color:var(--encre-2);
    display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .meta{display:flex;align-items:center;flex-wrap:wrap;gap:6px;font-size:13px;color:var(--encre-2)}
  .meta .pf{display:inline-flex}
  .meta .pf svg{display:block;width:15px;height:15px}
  .meta .sep{opacity:.5}
  .pastille{display:inline-flex;align-items:center;gap:6px;align-self:flex-start;font-size:12.5px;font-weight:500;
    padding:4px 10px;border-radius:999px;border:1px solid var(--trait);background:var(--fond);text-decoration:none}
  a.pastille:hover{border-color:var(--encre)}
  .pastille.attente{background:var(--chiffon);border-color:transparent}
  mark{background:var(--ambre);color:var(--sur-ambre);border-radius:3px;padding:0 2px}
  .vide{color:var(--encre-2);padding:28px 0}

  /* ---------- Demander : caché jusqu'à la découverte du serveur ---------- */
  body.demander-ouvert #bibliotheque{display:none}
  body.demander-ouvert .nav .nav-biblio{background:transparent;color:var(--encre-2)}
  body.demander-ouvert .nav .nav-demander{background:var(--actif-fond);color:var(--actif-encre)}
  .vue-demander{padding-top:28px;max-width:780px;margin:0 auto;overflow-wrap:anywhere}
  .demander-entete,.demander-contexte,.demander-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  .demander-entete{justify-content:space-between}
  .vue-demander .btn{margin-top:0;cursor:pointer;white-space:normal;text-align:left}
  .demander-contexte{padding:16px 18px;margin:24px 0 8px;background:var(--surface);border-radius:14px}
  .demander-contexte p{margin:0;flex:1;min-width:160px}
  .demander-contexte strong{display:block}
  .demander-note{font-size:13px;color:var(--encre-2);margin:8px 0 18px}
  .demander-inspiration summary{cursor:pointer;font-size:14px;font-weight:500}
  .demander-inspiration{margin:16px 0}
  .demander-exemples{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0 24px}
  .demander-exemples .btn{font-size:14px;font-weight:500;padding:9px 13px}
  .demander-messages{list-style:none;padding:0;margin:24px 0;display:flex;flex-direction:column;gap:16px}
  .demander-message{padding:18px 20px;border:1px solid var(--trait-fort);border-radius:14px;min-width:0}
  .demander-message.user{background:var(--surface);border-color:transparent}
  .demander-message h2{font-size:14px;margin:0 0 8px}
  .demander-texte{white-space:pre-wrap;overflow-wrap:anywhere;margin:0}
  .demander-sources{padding-left:20px;margin:16px 0 0;font-size:14px}
  .demander-sources li+li{margin-top:8px}
  .demander-sources a{text-underline-offset:3px}
  .demander-form label{display:block;font-weight:600;margin-bottom:8px}
  .demander-form textarea{display:block;width:100%;min-height:126px;resize:vertical;padding:14px 16px;
    border:1px solid var(--trait-fort);border-radius:12px;background:var(--fond);color:var(--encre);font:inherit}
  .demander-form textarea:focus{border-color:var(--encre)}
  .demander-actions{justify-content:space-between;margin-top:12px}
  .demander-actions .btn{background:var(--ambre);border-color:transparent;color:var(--sur-ambre)}
  .vue-demander button:disabled{opacity:.5;cursor:not-allowed}
  .demander-statut{min-height:1.6em;margin:18px 0 10px;white-space:pre-wrap}
  .demander-statut.erreur{padding:12px 16px;border-left:4px solid var(--ambre);background:var(--surface)}
  .fiche .demander-acces{margin-right:8px}

  /* ---------- fiche ---------- */
  .fiche,.vue-profil{display:none;padding-top:28px}
  .fiche:target,.vue-profil:target{display:block}
  body:has(.fiche:target) #bibliotheque, body:has(.vue-profil:target) #bibliotheque{display:none}
  .vue-profil .lecture{max-width:680px}
  .retour{display:inline-flex;align-items:center;gap:6px;color:var(--encre-2);font-weight:500;font-size:15px;text-decoration:none;margin-bottom:20px}
  .retour:hover{color:var(--encre)}
  .fiche-grille{display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:48px}
  .fiche h1{font-size:32px;font-weight:700;letter-spacing:-.02em;line-height:1.18;margin:0}
  .fiche .meta{margin-top:12px;font-size:14.5px}
  .btn{display:inline-flex;align-items:center;gap:8px;margin-top:18px;padding:10px 18px;border-radius:999px;
    font-weight:600;font-size:15px;text-decoration:none;border:1px solid var(--trait-fort);background:var(--fond)}
  .btn:hover{background:var(--surface)}
  .niveaux{display:none;background:var(--surface);border-radius:999px;padding:4px;margin-top:28px}
  .js .niveaux{display:flex;width:fit-content}
  .niveau{padding:8px 18px;border-radius:999px;border:0;background:transparent;font-weight:500;font-size:15px;color:var(--encre-2);cursor:pointer}
  .niveau[aria-selected="true"]{background:var(--fond);color:var(--encre);box-shadow:var(--ombre)}
  .aide{font-size:13.5px;color:var(--encre-3);margin:10px 0 0}
  .section-niveau{margin-top:26px}
  .js .section-niveau{display:none}
  .js .section-niveau.on{display:block}
  .titre-niveau{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--encre-3);margin:0 0 10px}
  .js .titre-niveau{display:none}
  .lecture{font-size:17px;line-height:1.72;max-width:680px}
  .lecture p{margin:0}
  .lecture p+p{margin-top:16px}
  .encadre{border-radius:14px;padding:18px 22px;max-width:680px;background:var(--chiffon)}
  .encadre strong{display:block;margin-bottom:6px}
  .chercher{display:none;align-items:center;gap:10px;background:var(--surface);border:2px solid transparent;
    border-radius:10px;padding:9px 13px;max-width:680px;margin-bottom:18px}
  .js .chercher{display:flex}
  .chercher:focus-within{border-color:var(--ambre);background:var(--fond)}
  .chercher input{border:0;outline:0;background:transparent;flex:1;font:inherit;color:var(--encre);min-width:0}
  .chercher .compte{font-size:13px;color:var(--encre-3);white-space:nowrap}
  .description{margin-top:26px;max-width:680px;border-top:1px solid var(--trait);padding-top:16px}
  .description summary{cursor:pointer;font-weight:600;font-size:15px}
  .description p{color:var(--encre-2);font-size:15.5px;white-space:pre-line;margin:12px 0 0}
  .encadre.platine{background:var(--surface)}
  .encadre.pourtoi{background:var(--fond);border:1px solid var(--trait-fort);position:relative;padding-left:26px}
  .encadre.pourtoi::before{content:"";position:absolute;left:0;top:16px;bottom:16px;width:4px;border-radius:0 4px 4px 0;background:var(--ambre)}
  .encadre + .encadre, .lecture + .encadre{margin-top:22px}
  .encadre-titre{display:flex;align-items:center;gap:10px;font-weight:600;margin-bottom:10px}
  .encadre-sous{margin-left:auto;font-size:13px;font-weight:500;color:var(--encre-3)}
  .retenir{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
  .retenir li{display:flex;gap:12px;align-items:flex-start}
  .num{width:24px;height:24px;border-radius:50%;background:var(--ambre);color:var(--sur-ambre);font-size:13px;font-weight:700;
    display:inline-flex;align-items:center;justify-content:center;flex:none;margin-top:1px}
  .memo h3{font-size:17px;font-weight:600;letter-spacing:-.01em;margin:26px 0 8px}
  .memo h3:first-child{margin-top:0}
  .memo ul,.memo ol{margin:0;padding-left:22px}
  .memo li+li{margin-top:6px}
  .encadre a{color:inherit;font-weight:600}
  .encadre p{margin:0}
  .encadre p+p{margin-top:10px}
  .profil-texte{white-space:pre-line}
  .description code{font-size:14px;background:var(--surface);padding:2px 6px;border-radius:6px;word-break:break-all}
  .cote h3{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--encre-3);margin:0 0 10px}
  .cote-bloc+.cote-bloc{margin-top:32px}
  .lie{display:block;text-decoration:none;padding:13px 0;border-top:1px solid var(--trait)}
  .lie strong{display:block;font-size:15px;font-weight:600;line-height:1.35}
  .lie:hover strong{text-decoration:underline;text-underline-offset:3px}
  .lie span{font-size:13px;color:var(--encre-2)}
  .themes-fiche{display:flex;flex-wrap:wrap;gap:8px}

  footer{margin-top:56px;padding-top:18px;border-top:1px solid var(--trait);color:var(--encre-3);font-size:12.5px;text-align:center;line-height:2}
  footer a{color:var(--lien)}

  @media (max-width:640px){
    .lien-carte{display:none}
    .lien-carte-mobile{display:inline-block}
    .tete-in{gap:8px;padding:10px 14px;flex-wrap:wrap}
    .nav{order:3;width:100%;justify-content:center}
    .vue-demander .demander-entete{align-items:flex-start}
    .marque{font-size:17px}
    .nav{margin-left:0;gap:2px}
    .nav a{padding:6px 9px;font-size:14px}
    .theme .tbtn{width:26px}
  }
  @media (max-width:860px){
    .tete-in{padding:12px 18px}
    .enveloppe{padding:0 18px 56px}
    .titre,.fiche h1{font-size:26px}
    .fiche-grille{grid-template-columns:1fr;gap:34px}
    .grille{grid-template-columns:1fr}
    .lecture{font-size:16.5px}
  }
</style>
</head>
<body>
<header class="tete">
  <div class="tete-in">
    <a class="marque" href="#bibliotheque"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="6.6" r="1.5"/><circle cx="12" cy="17.4" r="1.5"/><circle cx="6.6" cy="12" r="1.5"/><circle cx="17.4" cy="12" r="1.5"/></svg>Bobine</a>
    <nav class="nav" aria-label="Navigation">
      <a class="nav-biblio" href="#bibliotheque">Bibliothèque</a>
      <a class="nav-demander demander-acces" href="#demander" hidden>Demander</a>
      <a class="nav-profil" href="#profil">Profil</a>
    </nav>
    <div class="droite">
      <a class="lien-carte" href="graph.html">Carte des thèmes</a>
      <div class="theme" role="group" aria-label="Apparence">
        <button type="button" class="tbtn" data-m="light" title="Clair" aria-label="Apparence claire"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.5"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12h2.5M19 12h2.5M5 5l1.8 1.8M17.2 17.2L19 19M19 5l-1.8 1.8M6.8 17.2L5 19"/></svg></button>
        <button type="button" class="tbtn" data-m="dark" title="Sombre" aria-label="Apparence sombre"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 14.5A8.5 8.5 0 1 1 9.5 3.5a7 7 0 0 0 11 11Z"/></svg></button>
        <button type="button" class="tbtn" data-m="system" title="Comme l'appareil" aria-label="Apparence de l'appareil"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M9 20h6M12 16.5V20"/></svg></button>
      </div>
    </div>
  </div>
</header>

<main class="enveloppe">
  <section id="bibliotheque" aria-label="Bibliothèque">
    <h1 class="titre">Ta bibliothèque</h1>
    <p class="sous" id="stats">__COMPTE__</p>
    <label class="recherche">
      <svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
      <input id="q" type="search" placeholder="Cherche un sujet, un outil…" autocomplete="off" aria-label="Chercher dans tes vidéos">
    </label>
    <a class="lien-carte-mobile" href="graph.html">Voir la carte des thèmes</a>
    <div class="chips" id="chips" role="group" aria-label="Filtrer par thème">__CHIPS__</div>
    <div id="liste" class="grille">__GROUPES__</div>
    <p class="vide" id="vide" hidden>Aucune vidéo ne correspond. Essaie un autre mot, ou enlève le filtre.</p>
  </section>
__FICHES__
__PROFIL__
  <section class="vue-demander" id="demander" aria-labelledby="demander-titre" hidden>
    <a class="retour" href="#bibliotheque">← Bibliothèque</a>
    <div class="demander-entete">
      <h1 class="titre" id="demander-titre" tabindex="-1">Demander à Bobine</h1>
      <button class="btn" id="demander-nouveau" type="button">Nouvelle conversation</button>
    </div>
    <p class="sous">Retrouve une idée, compare des vidéos ou prépare ton prochain pas.</p>
    <div class="demander-contexte">
      <p>Ta sélection<strong id="demander-selection">Toute la bibliothèque</strong></p>
      <button class="btn" id="demander-global" type="button" hidden>Toute la bibliothèque</button>
    </div>
    <p class="demander-note" id="demander-aide-selection">Bobine cherche dans toute ta bibliothèque.</p>
    <details class="demander-inspiration">
    <summary>Besoin d’une idée de question ?</summary>
    <div class="demander-exemples" id="demander-exemples" role="group" aria-label="Exemples de questions, à modifier avant d’envoyer">
      <p class="demander-note">Ouvre une fiche pour poser une question</p>
    </div>
    </details>
    <ol class="demander-messages" id="demander-messages" aria-label="Conversation"></ol>
    <form class="demander-form" id="demander-form">
      <label for="demander-question">Ta question</label>
      <textarea id="demander-question" name="question" rows="4" maxlength="2000" required
        autocomplete="off" aria-describedby="demander-limite demander-confidentialite"
        placeholder="Que veux-tu retrouver dans tes vidéos ?" disabled></textarea>
      <div class="demander-actions">
        <span class="demander-note" id="demander-limite">2 000 caractères maximum · Ctrl ou ⌘ + Entrée pour envoyer</span>
        <button class="btn" id="demander-envoyer" type="submit" disabled>Envoyer</button>
      </div>
    </form>
    <p class="demander-statut" id="demander-statut" role="status" aria-live="polite" aria-atomic="true"></p>
    <button class="btn" id="demander-reconnecter" type="button" hidden>Reconnecter Bobine</button>
    <p class="demander-note">Bobine peut se tromper. Ouvre les fiches citées pour vérifier.</p>
    <p class="demander-note" id="demander-confidentialite">Conversation gardée uniquement dans cet onglet, effacée au rechargement.
      Les 6 derniers messages au maximum sont utilisés, avec des extraits limités.
      Ta question, ce court historique, ton profil s’il existe et les extraits utiles sont envoyés au service d’IA configuré.</p>
    <p class="demander-note">Une fiche sélectionnée limite les réponses à cette vidéo uniquement. Choisis « Toute la bibliothèque » pour croiser plusieurs vidéos.
      Changer de sélection commence une nouvelle conversation. Ton brouillon est conservé.</p>
  </section>
  <footer>Mis à jour le __DATE__ · __COUNT__<br>
  🎞️ écrit et réalisé par Wahid Rouhli · <a href="https://github.com/wrouhli/bobine">github.com/wrouhli/bobine</a></footer>
</main>

<script>
(function(){
  var racine = document.documentElement;
  racine.classList.add("js");

  /* ---- apparence : claire / sombre / appareil (même clé qu'avant) ---- */
  var tbtns = [].slice.call(document.querySelectorAll(".tbtn"));
  var CLE = "bobine-theme";
  var parametre = null;
  try { parametre = new URLSearchParams(location.search).get("theme"); } catch (e) {}
  function choisirTheme(mode, sauver){
    if (mode === "system") { racine.removeAttribute("data-theme"); } else { racine.setAttribute("data-theme", mode); }
    tbtns.forEach(function(b){ var on = b.dataset.m === mode; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on ? "true" : "false"); });
    if (sauver) { try { localStorage.setItem(CLE, mode); } catch (e) {} }
  }
  var initial = "system";
  if (parametre === "light" || parametre === "dark") { initial = parametre; }
  else { try { var v = localStorage.getItem(CLE); if (v === "light" || v === "dark" || v === "system") { initial = v; } } catch (e) {} }
  choisirTheme(initial, false);
  tbtns.forEach(function(b){ b.addEventListener("click", function(){ choisirTheme(b.dataset.m, true); }); });

  /* ---- outils ---- */
  function norm(s){ return (s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
  function esc(s){ return (s || "").replace(/[&<>"']/g, function(c){ return ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]; }); }
  function surligner(texte, requete){
    var t = esc(texte);
    if (!requete) { return t; }
    var motif = esc(requete).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    try { return t.replace(new RegExp("(" + motif + ")", "gi"), "<mark>$1</mark>"); } catch (e) { return t; }
  }
  function accord(n, mot){ return n + " " + mot + (n < 2 ? "" : "s"); }

  /* ---- recherche (titres, résumés, transcriptions) et filtres ---- */
  var q = document.getElementById("q");
  var stats = document.getElementById("stats");
  var vide = document.getElementById("vide");
  var cartes = [].slice.call(document.querySelectorAll(".carte"));
  var moisBlocs = [].slice.call(document.querySelectorAll(".mois"));
  var chips = [].slice.call(document.querySelectorAll(".chip"));
  var actifs = {};
  var total = cartes.length;
  var textes = null;
  function texteDe(c){
    if (!textes) { textes = {}; }
    if (!(c.dataset.fiche in textes)) {
      var f = document.getElementById(c.dataset.fiche);
      var transcript = f ? (f.querySelector(".transcript") || {}).textContent || "" : "";
      textes[c.dataset.fiche] = norm(c.dataset.text + " " + transcript);
    }
    return textes[c.dataset.fiche];
  }
  function nombreActifs(){ var n = 0; for (var t in actifs) { if (actifs[t]) { n++; } } return n; }
  function appliquer(){
    var requete = (q.value || "").trim(), nq = norm(requete), vus = 0;
    cartes.forEach(function(c){
      var themes = c.dataset.themes ? c.dataset.themes.split("|") : [];
      var ok = (!nq || texteDe(c).indexOf(nq) !== -1)
            && (nombreActifs() === 0 || themes.some(function(t){ return actifs[t]; }));
      c.hidden = !ok;
      if (ok) { vus++; }
      var tt = c.querySelector(".tt"), res = c.querySelector(".res");
      if (tt) { tt.innerHTML = surligner(c.dataset.titre || "", requete); }
      if (res) { res.innerHTML = surligner(c.dataset.contenu || "", requete); }
    });
    moisBlocs.forEach(function(m){
      var n = m.nextElementSibling, visible = false;
      while (n && !n.classList.contains("mois")) { if (n.classList.contains("carte") && !n.hidden) { visible = true; break; } n = n.nextElementSibling; }
      m.hidden = !visible;
    });
    var filtre = nq || nombreActifs();
    stats.textContent = filtre ? vus + " sur " + accord(total, "vidéo") : accord(total, "vidéo") + (total < 2 ? " enregistrée" : " enregistrées");
    vide.hidden = vus > 0 || total === 0;
    chips.forEach(function(p){
      var on = p.dataset.t === "" ? nombreActifs() === 0 : !!actifs[p.dataset.t];
      p.classList.toggle("on", on); p.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  chips.forEach(function(p){
    p.addEventListener("click", function(){
      var t = p.dataset.t;
      if (t === "") { actifs = {}; } else if (actifs[t]) { delete actifs[t]; } else { actifs[t] = true; }
      appliquer();
    });
  });
  q.addEventListener("input", appliquer);
  document.addEventListener("keydown", function(ev){
    var cible = ev.target && ev.target.tagName;
    if (ev.key === "/" && cible !== "INPUT" && cible !== "TEXTAREA") { ev.preventDefault(); location.hash = "bibliotheque"; q.focus(); }
  });
  /* filtre venu de la carte des thèmes : vault.html?theme=ia */
  if (parametre && parametre !== "light" && parametre !== "dark") {
    chips.forEach(function(p){ if (p.dataset.t && p.dataset.t.toLowerCase() === parametre.toLowerCase()) { actifs[p.dataset.t] = true; } });
  }
  [].slice.call(document.querySelectorAll("[data-filtre]")).forEach(function(b){
    b.addEventListener("click", function(){ actifs = {}; actifs[b.dataset.filtre] = true; appliquer(); });
  });
  appliquer();

  /* ---- fiche : niveaux de lecture et recherche dans la transcription ---- */
  [].slice.call(document.querySelectorAll(".fiche")).forEach(function(fiche){
    var boutons = [].slice.call(fiche.querySelectorAll(".niveau"));
    var sections = [].slice.call(fiche.querySelectorAll(".section-niveau"));
    var aide = fiche.querySelector(".aide");
    function montrer(nom){
      boutons.forEach(function(b){ b.setAttribute("aria-selected", b.dataset.niveau === nom ? "true" : "false"); });
      sections.forEach(function(s){ s.classList.toggle("on", s.dataset.niveau === nom); });
      var b = boutons.filter(function(x){ return x.dataset.niveau === nom; })[0];
      if (aide && b) { aide.textContent = b.dataset.aide || ""; }
    }
    boutons.forEach(function(b){ b.addEventListener("click", function(){ montrer(b.dataset.niveau); }); });
    [].slice.call(fiche.querySelectorAll("[data-vers]")).forEach(function(l){
      l.addEventListener("click", function(ev){ ev.preventDefault(); montrer(l.dataset.vers); });
    });
    montrer(boutons.length ? boutons[0].dataset.niveau : "bref");

    var champ = fiche.querySelector(".chercher input"), compte = fiche.querySelector(".chercher .compte");
    var paragraphes = [].slice.call(fiche.querySelectorAll(".transcript p"));
    paragraphes.forEach(function(p){ p.dataset.brut = p.textContent; });
    if (champ) {
      champ.addEventListener("input", function(){
        var r = champ.value.trim(), nr = norm(r), n = 0, premier = null;
        paragraphes.forEach(function(p){
          var trouve = !!nr && norm(p.dataset.brut).indexOf(nr) !== -1;
          p.innerHTML = trouve ? surligner(p.dataset.brut, r) : esc(p.dataset.brut);
          if (trouve) { n++; if (!premier) { premier = p; } }
        });
        compte.textContent = nr ? accord(n, "passage") : "";
        if (premier) { premier.scrollIntoView({ block: "center" }); }
      });
    }
  });

  /* ---- navigation : on retrouve sa place dans la bibliothèque ---- */
  var position = 0;
  function versHaut(){ window.scrollTo(0, 0); }
  window.addEventListener("hashchange", function(){
    var h = location.hash.slice(1);
    if ((h.indexOf("f-") === 0 || h === "profil" || h === "demander") && document.getElementById(h)) { versHaut(); }
    else { window.scrollTo(0, position); }
  });
  cartes.forEach(function(c){ c.addEventListener("click", function(){ position = window.scrollY; }); });
})();

/* ---- Demander : état privé à l'onglet, aucune persistance ---- */
(function(){
  "use strict";
  // Une copie locale/iCloud n'essaie jamais de contacter un serveur.
  if (location.protocol !== "http:" && location.protocol !== "https:") { return; }
  if (!window.fetch || !window.AbortController) { return; }

  var vue = document.getElementById("demander");
  var titre = document.getElementById("demander-titre");
  var formulaire = document.getElementById("demander-form");
  var question = document.getElementById("demander-question");
  var envoyerBouton = document.getElementById("demander-envoyer");
  var nouveau = document.getElementById("demander-nouveau");
  var global = document.getElementById("demander-global");
  var selection = document.getElementById("demander-selection");
  var messages = document.getElementById("demander-messages");
  var statut = document.getElementById("demander-statut");
  var reconnecter = document.getElementById("demander-reconnecter");
  var acces = Array.from(document.querySelectorAll(".demander-acces"));
  var aideSelection = document.getElementById("demander-aide-selection");
  var boiteExemples = document.getElementById("demander-exemples");
  var exemples = [];
  var navigation = Array.from(document.querySelectorAll(".nav a"));
  var fiches = new Map();
  document.querySelectorAll("article.fiche").forEach(function(f){
    if (/^f-[A-Za-z0-9_-]+$/.test(f.id)) { fiches.set(f.id, f); }
  });
  var jeton = null, decouvert = false, enCours = false, verification = false;
  var ficheChoisie = null, historique = [];

  function annoncer(texte, erreur){
    statut.textContent = texte;
    statut.classList.toggle("erreur", !!erreur);
  }
  function actualiser(){
    // Après une panne, la conversation reste consultable mais l'envoi est bloqué.
    question.disabled = false;
    question.readOnly = enCours;
    envoyerBouton.disabled = !jeton || enCours || verification || !question.value.trim() || question.value.length > 2000;
    envoyerBouton.textContent = enCours ? "Bobine cherche…" : "Envoyer";
    nouveau.disabled = enCours || verification;
    global.disabled = enCours || verification;
    reconnecter.disabled = enCours || verification;
    exemples.forEach(function(b){ b.disabled = enCours || verification; });
    formulaire.setAttribute("aria-busy", enCours ? "true" : "false");
  }
  function naviguer(prendreFocus){
    var ouverte = decouvert && location.hash === "#demander";
    vue.hidden = !ouverte;
    document.body.classList.toggle("demander-ouvert", ouverte);
    navigation.forEach(function(a){
      var active = a.getAttribute("href") === (ouverte ? "#demander" : location.hash === "#profil" ? "#profil" : "#bibliotheque");
      if (active) { a.setAttribute("aria-current", "page"); } else { a.removeAttribute("aria-current"); }
    });
    if (ouverte && prendreFocus) { titre.focus(); }
  }
  function viserQuestion(){ if (!vue.hidden) { question.focus(); } }
  function effacer(garderBrouillon){
    historique = [];
    while (messages.firstChild) { messages.removeChild(messages.firstChild); }
    if (!garderBrouillon) { question.value = ""; }
    if (jeton) { annoncer("Nouvelle conversation. À toi de poser ta question.", false); }
    actualiser();
  }
  function proposerQuestions(){
    while (boiteExemples.firstChild) { boiteExemples.removeChild(boiteExemples.firstChild); }
    exemples = [];
    var sujets = [], vus = new Set();
    function ajouterSujet(texte){
      if (typeof texte !== "string") { return; }
      var sujet = texte.trim().replace(/\s+/g, " ").slice(0, 200);
      if (!sujet || vus.has(sujet.toLowerCase())) { return; }
      vus.add(sujet.toLowerCase()); sujets.push(sujet);
    }
    if (ficheChoisie) {
      fiches.get(ficheChoisie).querySelectorAll(".themes-fiche [data-filtre]").forEach(function(p){
        ajouterSujet(p.dataset.filtre);
      });
      if (!sujets.length) { ajouterSujet(fiches.get(ficheChoisie).querySelector("h1").textContent); }
    } else {
      document.querySelectorAll("#chips .chip[data-t]").forEach(function(p){ ajouterSujet(p.dataset.t); });
      if (!sujets.length) { fiches.forEach(function(f){ ajouterSujet(f.querySelector("h1").textContent); }); }
    }
    sujets.slice(0, 3).forEach(function(sujet){
      var b = document.createElement("button");
      b.className = "btn";
      b.setAttribute("type", "button");
      b.dataset.question = "Que retenir sur « " + sujet + " » dans " + (ficheChoisie ? "cette vidéo ?" : "mes vidéos ?");
      b.textContent = b.dataset.question;
      boiteExemples.appendChild(b); exemples.push(b);
    });
    exemples.forEach(function(b){ b.addEventListener("click", function(){
      if (enCours || verification) { return; }
      question.value = b.dataset.question; actualiser(); viserQuestion();
    }); });
    if (!exemples.length) {
      var aide = document.createElement("p");
      aide.className = "demander-note";
      aide.textContent = "Ouvre une fiche pour poser une question";
      boiteExemples.appendChild(aide);
    }
  }
  function choisirFiche(id){
    if (enCours || verification || (id && !fiches.has(id))) { return; }
    if (ficheChoisie !== id) { effacer(true); }
    ficheChoisie = id;
    selection.textContent = id ? fiches.get(id).querySelector("h1").textContent : "Toute la bibliothèque";
    global.hidden = !id;
    aideSelection.textContent = id
      ? "Bobine répond uniquement à partir de cette vidéo, sans chercher dans les autres fiches."
      : "Bobine cherche dans toute ta bibliothèque.";
    proposerQuestions();
  }
  function ajouterMessage(role, texte, sources){
    var bloc = document.createElement("li");
    bloc.className = "demander-message " + role;
    bloc.setAttribute("tabindex", "-1");
    var auteur = document.createElement("h2");
    auteur.textContent = role === "user" ? "Toi" : "Bobine";
    var contenu = document.createElement("p");
    contenu.className = "demander-texte";
    contenu.textContent = texte; // Pas de Markdown, de HTML ni de liens automatiques.
    bloc.appendChild(auteur);
    bloc.appendChild(contenu);
    var liste = document.createElement("ul"), vus = new Set(), bibliothequeActualisee = false;
    liste.className = "demander-sources";
    liste.setAttribute("aria-label", "Fiches sources");
    (sources || []).slice(0, 20).forEach(function(source){
      // Seules les ancres validées renvoyées par le serveur sont admises, jamais un lien du modèle.
      if (!source || typeof source.id !== "string" || typeof source.ancre !== "string"
          || !/^#f-[A-Za-z0-9_-]+$/.test(source.ancre) || source.ancre !== "#" + source.id
          || source.ancre !== source.ancre.trim() || vus.has(source.id)) { return; }
      vus.add(source.id);
      var locale = fiches.has(source.id);
      var li = document.createElement("li"), lien = document.createElement("a");
      // Une fiche ajoutée depuis l'ouverture de l'onglet reste consultable sans perdre la conversation.
      lien.setAttribute("href", locale ? source.ancre : "vault.html" + source.ancre);
      if (!locale) {
        lien.setAttribute("target", "_blank");
        lien.setAttribute("rel", "noopener noreferrer");
        bibliothequeActualisee = true;
      }
      lien.textContent = typeof source.titre === "string" && source.titre.trim()
        ? source.titre.slice(0, 300) : locale ? fiches.get(source.id).querySelector("h1").textContent : "Fiche source";
      li.appendChild(lien);
      liste.appendChild(li);
    });
    if (liste.firstChild) { bloc.appendChild(liste); }
    if (bibliothequeActualisee) {
      var note = document.createElement("p");
      note.className = "demander-note";
      note.textContent = "Ta bibliothèque a été actualisée. Les nouvelles fiches s’ouvrent dans un nouvel onglet avec la page actualisée. Cette conversation reste ici.";
      bloc.appendChild(note);
    }
    messages.appendChild(bloc);
    while (messages.children.length > 6) { messages.removeChild(messages.firstChild); }
    return bloc;
  }
  async function requeteJSON(url, options, delai){
    var controle = new AbortController();
    var minuterie = setTimeout(function(){ controle.abort(); }, delai);
    try {
      var reponse = await fetch(url, Object.assign({}, options, {
        credentials: "same-origin", mode: "same-origin", cache: "no-store",
        redirect: "error", signal: controle.signal
      }));
      var estJSON = /^application\/json\b/i.test(reponse.headers.get("Content-Type") || "");
      if (!reponse.ok) {
        var e = new Error("http");
        e.statut = reponse.status;
        e.attente = lireAttente(reponse.headers.get("Retry-After"));
        if (estJSON) {
          try {
            var detail = await reponse.json();
            if (detail && typeof detail.code === "string" && /^[a-z_]{1,64}$/.test(detail.code)) { e.code = detail.code; }
            if (detail && typeof detail.erreur === "string") { e.erreur = detail.erreur.slice(0, 500); }
          } catch (_) { /* Un corps illisible n'efface pas le statut HTTP. */ }
        }
        throw e;
      }
      if (!estJSON) { throw new Error("format"); }
      return await reponse.json();
    } finally { clearTimeout(minuterie); }
  }
  async function verifier(){
    if (verification || enCours) { return; }
    verification = true;
    if (decouvert) { annoncer("Connexion à Bobine…", false); actualiser(); }
    try {
      var etat = await requeteJSON("/api/bobine", {method: "GET", headers: {"Accept": "application/json"}}, 5000);
      // Le jeton opaque n'est jamais écrit dans la page, une URL ou un stockage.
      if (!etat || etat.disponible !== true || typeof etat.jeton !== "string"
          || !/^[\x21-\x7e]{1,512}$/.test(etat.jeton)) { throw new Error("indisponible"); }
      jeton = etat.jeton;
      var premiere = !decouvert;
      decouvert = true;
      acces.forEach(function(a){
        a.hidden = !!a.dataset.demanderFiche && !fiches.has(a.dataset.demanderFiche);
      });
      reconnecter.hidden = true;
      if (!premiere) { annoncer("Bobine est reconnecté. Tu peux envoyer ta question quand tu veux.", false); }
      naviguer(premiere);
    } catch (e) {
      jeton = null;
      // Une découverte ratée est silencieuse : la bibliothèque demeure le repli.
      if (decouvert) {
        annoncer("Bobine est indisponible. Ta question et la conversation restent ici. Réessaie la connexion dans un instant.", true);
        reconnecter.hidden = false;
      }
    } finally {
      verification = false;
      if (decouvert) { actualiser(); }
    }
  }
  function lireAttente(valeur){
    if (typeof valeur !== "string") { return 0; }
    valeur = valeur.trim();
    var secondes = 0;
    if (/^\d{1,6}$/.test(valeur)) { secondes = Number(valeur); }
    else if (/^[A-Za-z]{3}, \d{2} [A-Za-z]{3} \d{4} \d{2}:\d{2}:\d{2} GMT$/.test(valeur)) {
      secondes = Math.ceil((Date.parse(valeur) - Date.now()) / 1000);
    }
    // Pas de délai absurde, négatif ou dépassant une journée.
    return Number.isFinite(secondes) && secondes > 0 && secondes <= 86400 ? secondes : 0;
  }
  function erreurEnvoi(e){
    var textes = {
      400: "Cette question n’a pas pu être envoyée. Vérifie son texte et réessaie.",
      401: "La connexion à Bobine a expiré. Reconnecte Bobine avant d’envoyer.",
      403: "Bobine n’autorise plus cette connexion. Reconnecte Bobine avant d’envoyer.",
      409: "Bobine répond déjà à une question. Attends un instant avant de réessayer.",
      429: "Bobine a reçu trop de demandes. Attends un instant avant de réessayer.",
      502: "Le service d’IA n’a pas pu répondre. Tu peux réessayer dans un instant.",
      503: "Bobine est indisponible. Réessaie la connexion dans un instant.",
      504: "La réponse prend trop de temps. Attends un instant avant de réessayer."
    };
    var codes = {
      cle_refusee: "Le service d’IA refuse la clé configurée. Vérifie la clé dans les réglages de Bobine avant de réessayer.",
      cle_absente: "Ajoute une clé de service dans les réglages de Bobine pour poser une question.",
      configuration_invalide: "Les réglages du service d’IA doivent être vérifiés avant de réessayer.",
      compteur_indisponible: "Le compteur de demandes est indisponible. Fais vérifier le compteur de Bobine avant de réessayer.",
      fiche_introuvable: "Cette fiche n’est plus disponible. Ouvre la bibliothèque actualisée pour choisir une vidéo.",
      fiche_invalide: "Choisis une fiche depuis la bibliothèque avant de réessayer.",
      question_invalide: "Écris une question de 1 à 2 000 caractères.",
      question_trop_longue: "Cette question est trop longue. Raccourcis-la avant de réessayer.",
      demande_trop_longue: "Cette demande est trop longue. Raccourcis ta question avant de réessayer.",
      historique_invalide: "La conversation ne peut pas être utilisée. Commence une nouvelle conversation.",
      bibliotheque_indisponible: "La bibliothèque n’est pas lisible pour le moment. Fais vérifier les fiches avant de réessayer.",
      reponse_invalide: "La réponse reçue n’est pas lisible. Essaie de reformuler ta question.",
      reponse_non_verifiable: "Bobine n’a pas pu vérifier les sources de cette réponse. Essaie une question plus précise.",
      fournisseur_indisponible: "Le service d’IA est indisponible pour le moment. Réessaie plus tard.",
      delai_depasse: textes[504]
    };
    var texte = e.name === "AbortError" ? textes[504]
      : Object.prototype.hasOwnProperty.call(codes, e.code) ? codes[e.code]
      : textes[e.statut] || "Impossible de recevoir la réponse de Bobine. Vérifie la connexion.";
    if (e.statut === 429) {
      // Le serveur emploie « limite » pour les deux quotas. Son texte sert seulement à les distinguer.
      // Aucun message technique ni texte inconnu reçu du serveur n'est affiché tel quel.
      var quotidienne = e.attente === 86400 || (e.code === "limite" && /quotidien|demain/i.test(e.erreur || ""));
      if (quotidienne) { texte = "La limite quotidienne de questions est atteinte. Réessaie demain."; }
      else if (e.attente) {
        var minutes = Math.ceil(e.attente / 60);
        var duree = minutes === 1 ? "une minute" : minutes <= 60 ? minutes + " minutes" : Math.ceil(minutes / 60) + " heures";
        texte = "Bobine a reçu trop de demandes. Patiente " + duree + " avant de réessayer.";
      } else { texte = "Bobine a reçu trop de demandes. Patiente une minute avant de réessayer."; }
    }
    if (!e.statut || e.statut === 401 || e.statut === 403 || e.statut === 503) {
      jeton = null;
      reconnecter.hidden = false;
    }
    annoncer(texte + " Ta question est conservée. Aucun nouvel envoi automatique.", true);
  }
  async function envoyer(ev){
    ev.preventDefault();
    if (enCours || verification || !jeton) { return; }
    var texte = question.value.trim();
    if (!texte || question.value.length > 2000) {
      annoncer("Écris une question de 1 à 2 000 caractères.", true); viserQuestion(); return;
    }
    var demande = {question: texte, historique: historique.slice(-6)};
    if (ficheChoisie) { demande.fiche = ficheChoisie; }
    enCours = true;
    actualiser();
    annoncer("Bobine cherche dans ta sélection…", false);
    try {
      var resultat = await requeteJSON("/api/demander", {
        method: "POST", headers: {"Content-Type": "application/json", "Accept": "application/json", "X-Bobine-Token": jeton},
        body: JSON.stringify(demande)
      }, 65000);
      if (!resultat || typeof resultat.reponse !== "string" || !resultat.reponse.trim()
          || resultat.reponse.length > 12000 || !Array.isArray(resultat.sources)) { throw new Error("format"); }
      ajouterMessage("user", texte);
      var derniereReponse = ajouterMessage("assistant", resultat.reponse, resultat.sources);
      // Le serveur applique le même budget : 6 messages, 800 caractères chacun.
      historique = historique.concat([
        {role: "user", content: texte.slice(0, 800)},
        {role: "assistant", content: resultat.reponse.slice(0, 800)}
      ]).slice(-6);
      question.value = "";
      annoncer("La réponse est prête. Consulte les fiches sources pour vérifier.", false);
    } catch (e) { erreurEnvoi(e); }
    finally {
      enCours = false; actualiser();
      if (derniereReponse && !vue.hidden) { derniereReponse.focus(); } else { viserQuestion(); }
    }
  }
  acces.forEach(function(a){
    a.addEventListener("click", function(ev){
      if (!decouvert) { ev.preventDefault(); return; }
      if (a.dataset.demanderFiche) { choisirFiche(a.dataset.demanderFiche); }
    });
  });
  nouveau.addEventListener("click", function(){
    if (enCours || verification) { return; }
    effacer(false); viserQuestion();
  });
  global.addEventListener("click", function(){ choisirFiche(null); viserQuestion(); });
  reconnecter.addEventListener("click", verifier);
  question.addEventListener("input", actualiser);
  question.addEventListener("keydown", function(ev){
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { envoyer(ev); }
  });
  formulaire.addEventListener("submit", envoyer);
  window.addEventListener("hashchange", function(){ naviguer(true); });
  proposerQuestions();
  naviguer(false);
  verifier();
})();
/* ---- fin Demander ---- */
</script>
</body>
</html>
"""


TEMPLATE_GRAPHE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Vault · carte des thèmes</title>
<link rel="icon" href="__FAVICON__">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#FFFFFF">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#000000">
<style>
  :root{
    --bg:#FFFFFF; --ink:#000000; --ink2:rgba(0,0,0,.62); --muted:rgba(0,0,0,.45); --line:rgba(0,0,0,.09);
    --panel:#FFFFFF; --violet:#FEC90A; --lien:#000000; --btnactive:rgba(0,0,0,.08);
    --grad-old:#BFBFBF; --grad-new:#FEC90A; --statique-bg:#000000; --sur-bouton:#000000;
    --ombre:0 12px 40px rgba(0,0,0,.14);
  }
  :root[data-theme="dark"]{
    --bg:#000000; --ink:#FFFFFF; --ink2:rgba(255,255,255,.68); --muted:rgba(255,255,255,.48); --line:rgba(255,255,255,.12);
    --panel:rgba(18,18,18,.94); --violet:#FEC90A; --lien:#FEC90A; --btnactive:rgba(255,255,255,.12);
    --grad-old:#5C5C5C; --grad-new:#FEC90A; --sur-bouton:#000000;
    --ombre:0 12px 40px rgba(0,0,0,.6);
  }
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      --bg:#000000; --ink:#FFFFFF; --ink2:rgba(255,255,255,.68); --muted:rgba(255,255,255,.48); --line:rgba(255,255,255,.12);
      --panel:rgba(18,18,18,.94); --violet:#FEC90A; --lien:#FEC90A; --btnactive:rgba(255,255,255,.12);
      --grad-old:#5C5C5C; --grad-new:#FEC90A; --sur-bouton:#000000;
      --ombre:0 12px 40px rgba(0,0,0,.6);
    }
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;overflow:hidden}
  body{background:var(--bg);color:var(--ink);
       font:14px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Inter,Roboto,Arial,sans-serif;
       -webkit-font-smoothing:antialiased}
  canvas{display:none;touch-action:none}
  #statique{position:fixed;inset:0;width:100%;height:100%;background:var(--statique-bg)}
  header{position:fixed;top:0;left:0;right:0;display:flex;align-items:center;gap:14px;
         padding:14px 16px;z-index:2;pointer-events:none;flex-wrap:wrap}
  .brand{font-size:15px;font-weight:650}
  .brand .reel{color:var(--ink);margin-right:6px;position:relative;top:2px}
  header #stats{color:var(--muted);font-size:13px;flex:1;white-space:nowrap}
  header a.lien{pointer-events:auto;color:var(--lien);text-decoration:none;font-weight:500}
  header a.lien:hover{text-decoration:underline;text-underline-offset:3px}
  .theme{pointer-events:auto;display:flex;gap:2px;background:var(--panel);border:1px solid var(--line);
         border-radius:9px;padding:2px}
  .tbtn{width:27px;height:24px;display:grid;place-items:center;border:0;background:transparent;
        border-radius:7px;color:var(--muted);cursor:pointer;padding:0}
  .tbtn:hover{color:var(--ink)}
  .tbtn.on{background:var(--btnactive);color:var(--ink)}
  #zoom{position:fixed;right:14px;bottom:64px;display:flex;flex-direction:column;gap:8px;z-index:3}
  #zoom button{width:34px;height:34px;border-radius:9px;border:1px solid var(--line);
               background:var(--panel);color:var(--ink2);font-size:17px;cursor:pointer}
  #zoom button:hover{color:var(--ink)}
  #aimant{margin-bottom:6px}
  #aimant.on{background:var(--btnactive);color:var(--ink)}
  #legende{position:fixed;left:16px;bottom:46px;z-index:2;pointer-events:none;
           color:var(--muted);font-size:12px;line-height:1.9}
  #legende .puce{display:inline-block;width:9px;height:9px;border-radius:50%;
                 background:var(--grad-old);margin-right:6px;vertical-align:-1px}
  #legende .puce.theme{width:12px;height:12px;background:var(--violet);
                       box-shadow:0 0 8px var(--violet);margin-right:6px}
  #degrade{display:inline-block;width:72px;height:8px;border-radius:4px;margin:0 6px;vertical-align:-1px;
           background:linear-gradient(90deg, var(--grad-old), var(--grad-new))}
  #hint{position:fixed;bottom:34px;left:0;right:0;text-align:center;color:var(--muted);
        font-size:12px;z-index:2;pointer-events:none;padding:0 16px}
  #signature{position:fixed;bottom:10px;left:0;right:0;text-align:center;color:var(--muted);
             font-size:11.5px;z-index:2;pointer-events:none}
  #signature a{pointer-events:auto;color:var(--lien);text-decoration:none}
  #apercu{position:fixed;left:50%;transform:translateX(-50%);bottom:18px;
          width:min(520px, calc(100vw - 28px));background:var(--panel);
          border:1px solid var(--line);border-radius:16px;padding:16px 18px 14px;
          z-index:4;display:none;box-shadow:var(--ombre);backdrop-filter:blur(10px);
          -webkit-backdrop-filter:blur(10px)}
  #apercu h2{font-size:16px;margin:0 24px 4px 0;line-height:1.4;font-weight:620}
  #apercu .meta{color:var(--muted);font-size:12.5px;margin-bottom:8px}
  #apercu p{margin:0 0 12px;color:var(--ink2);font-size:13.5px;line-height:1.55;
            max-height:5.6em;overflow:hidden}
  #apercu .actions{display:flex;gap:10px;flex-wrap:wrap}
  #apercu .actions a{text-decoration:none;font-size:13px;font-weight:600;padding:7px 12px;
                     border-radius:9px;border:1px solid var(--line);color:var(--ink2)}
  #apercu .actions a:hover{border-color:var(--ink);color:var(--ink)}
  #apercu .actions a.premier{background:var(--violet);border-color:transparent;
                             color:var(--sur-bouton)}
  #fermer{position:absolute;top:8px;right:10px;border:0;background:transparent;
          color:var(--muted);font-size:15px;cursor:pointer;padding:4px 6px;line-height:1}
  #fermer:hover{color:var(--ink)}
</style>
</head>
<body>
<header>
  <span class="brand"><svg class="reel" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="8.6"/><circle cx="12" cy="12" r="2.1" fill="currentColor" stroke="none"/><circle cx="12" cy="5.7" r="1.5" fill="currentColor" stroke="none"/><circle cx="12" cy="18.3" r="1.5" fill="currentColor" stroke="none"/><circle cx="5.7" cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="18.3" cy="12" r="1.5" fill="currentColor" stroke="none"/></svg>Carte des thèmes</span>
  <span id="stats">__STATS_G__</span>
  <div class="theme" role="group" aria-label="Thème">
    <button type="button" class="tbtn" data-m="light" title="Clair" aria-label="Thème clair"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.5"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12h2.5M19 12h2.5M5 5l1.8 1.8M17.2 17.2L19 19M19 5l-1.8 1.8M6.8 17.2L5 19"/></svg></button>
    <button type="button" class="tbtn" data-m="dark" title="Sombre" aria-label="Thème sombre"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14.5A8.5 8.5 0 1 1 9.5 3.5a7 7 0 0 0 11 11Z"/></svg></button>
    <button type="button" class="tbtn" data-m="system" title="Système" aria-label="Thème système"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 3.5a8.5 8.5 0 0 0 0 17Z" fill="currentColor" stroke="none"/></svg></button>
  </div>
  <a class="lien" href="vault.html">← Bibliothèque</a>
</header>
<div id="zoom"><button id="aimant" aria-label="Aimant : les points reviennent en place" aria-pressed="true" title="Aimant : les points reviennent en place"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M6 3v8a6 6 0 0 0 12 0V3"/><rect x="6" y="3" width="4" height="3.2" rx="0.8" fill="currentColor" stroke="none"/><rect x="14" y="3" width="4" height="3.2" rx="0.8" fill="currentColor" stroke="none"/></svg></button><button id="zi" aria-label="Zoom avant">+</button><button id="zo" aria-label="Zoom arrière">−</button></div>
<div id="legende">
  <div><span class="puce"></span>vidéo · <span class="puce theme"></span>thème (taille = nombre de fiches)</div>
  <div>date : ancien <span id="degrade"></span> récent</div>
</div>
<div id="hint">Clique un thème pour filtrer la liste · une vidéo pour l'aperçu · glisse pour déplacer (🧲 règle le retour) · pince pour zoomer</div>
<div id="signature">🎞️ écrit et réalisé par Wahid Rouhli · <a href="https://github.com/wrouhli/bobine">github.com/wrouhli/bobine</a></div>
<div id="apercu" role="dialog" aria-label="Aperçu de la fiche">
  <button id="fermer" aria-label="Fermer">✕</button>
  <h2 id="ap-titre"></h2>
  <div class="meta" id="ap-meta"></div>
  <p id="ap-contenu"></p>
  <div class="actions">
    <a id="ap-fiche" class="premier" href="vault.html">Lire la fiche</a>
    <a id="ap-video" href="#" target="_blank" rel="noopener noreferrer">Voir la vidéo ↗</a>
    <a id="ap-theme" href="#">Explorer ce thème</a>
  </div>
</div>
<canvas id="c"></canvas>
__SVG__
<script>
const FICHES = __ENTREES__;
const THEMES = __THEMES__;
(function(){
  /* ---- thème clair / sombre / système (même clé que la liste) ---- */
  var racine = document.documentElement;
  var tbtns = [].slice.call(document.querySelectorAll(".tbtn"));
  var CLE = "bobine-theme";
  var force = null;
  try { force = new URLSearchParams(location.search).get("theme"); } catch (e) {}
  var PALETTES = {
    light: { fond:"#FFFFFF", halo:null, theme:"#FEC90A", themeLabel:"#000000",
             fiche:"#9E9E9E", ficheLabel:"rgba(0,0,0,.62)", lien:"rgba(0,0,0,.12)",
             lienFort:"rgba(0,0,0,.55)", ancien:"#BFBFBF", recent:"#FEC90A" },
    dark:  { fond:"#000000", halo:"rgba(254,201,10,.10)", theme:"#FEC90A", themeLabel:"#FFFFFF",
             fiche:"#8A8A8A", ficheLabel:"rgba(255,255,255,.62)", lien:"rgba(255,255,255,.16)",
             lienFort:"rgba(254,201,10,.75)", ancien:"#5C5C5C", recent:"#FEC90A" }
  };
  var pal = PALETTES.light;
  function pluriel(n, mot){ return n + " " + mot + (n < 2 ? "" : "s"); }
  function themeEffectif(){
    var m = racine.getAttribute("data-theme");
    if (m === "dark" || m === "light") { return m; }
    return (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
  }
  function choisirTheme(mode, sauver){
    if (mode === "system") { racine.removeAttribute("data-theme"); }
    else { racine.setAttribute("data-theme", mode); }
    tbtns.forEach(function(b){
      var on = b.dataset.m === mode;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (sauver) { try { localStorage.setItem(CLE, mode); } catch (e) {} }
    appliquerTheme();
  }
  function appliquerTheme(){ pal = PALETTES[themeEffectif()]; dessiner(); }
  var initial = "system";
  if (force === "light" || force === "dark") { initial = force; }
  else { try { var v = localStorage.getItem(CLE); if (v === "light" || v === "dark" || v === "system") { initial = v; } } catch (e) {} }
  tbtns.forEach(function(b){ b.addEventListener("click", function(){ choisirTheme(b.dataset.m, true); }); });
  if (window.matchMedia) { try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", appliquerTheme); } catch (e) {} }

  /* ---- aimant : les points reviennent en place, ou restent posés ---- */
  var aimant = true;
  try { if (localStorage.getItem("bobine-carte-aimant") === "0") { aimant = false; } } catch (e) {}
  var poses = {};
  var btnAimant = document.getElementById("aimant");
  function majAimant(){
    btnAimant.classList.toggle("on", aimant);
    var texte = aimant ? "Aimant allumé : les points reviennent en place" : "Libre : les points restent où tu les poses";
    btnAimant.title = texte;
    btnAimant.setAttribute("aria-label", texte);
    btnAimant.setAttribute("aria-pressed", aimant ? "true" : "false");
  }
  btnAimant.addEventListener("click", function(){
    aimant = !aimant;
    try { localStorage.setItem("bobine-carte-aimant", aimant ? "1" : "0"); } catch (e) {}
    majAimant();
    if (aimant) { poses = {}; lancerRetour(null); }
  });
  majAimant();

  /* ---- données : fiches, thèmes, liens, couleurs de date ---- */
  var nf = FICHES.length;
  var nodes = [], edges = [], themeIdx = new Map();
  FICHES.forEach(function(f, i){
    nodes.push({ type: "fiche", fiche: f, x: 0, y: 0, r: 5, t: null });
  });
  THEMES.forEach(function(t, k){
    themeIdx.set(t.nom, nf + k);
    nodes.push({ type: "theme", label: t.nom, n: t.n, x: 0, y: 0, r: 9 + 3 * Math.sqrt(t.n) });
  });
  FICHES.forEach(function(f, i){
    (f.themes || []).forEach(function(t){
      var j = themeIdx.get(t);
      if (j !== undefined) { edges.push({ s: i, t: j }); }
    });
  });
  var dates = FICHES.map(function(f){ return f.date || ""; }).filter(function(d){ return d; }).sort();
  function jours(d){ var p = d.split("-"); return Date.UTC(+p[0], +p[1] - 1, +p[2]); }
  var tMin = dates.length ? jours(dates[0]) : 0;
  var tMax = dates.length ? jours(dates[dates.length - 1]) : 0;
  FICHES.forEach(function(f, i){
    if (f.date && tMax > tMin) { nodes[i].t = (jours(f.date) - tMin) / (tMax - tMin); }
  });
  function melange(a, b, t){
    function c(h){ return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)]; }
    var A = c(a), B = c(b);
    return "rgb(" + Math.round(A[0] + (B[0] - A[0]) * t) + ","
                  + Math.round(A[1] + (B[1] - A[1]) * t) + ","
                  + Math.round(A[2] + (B[2] - A[2]) * t) + ")";
  }
  function couleurFiche(n){
    if (n.t === null) { return pal.fiche; }
    return melange(pal.ancien, pal.recent, n.t);
  }
  /* position de départ : précalculée en Python (stable d'une génération à l'autre) */
  var POS = __POS__;
  if (POS && POS.length === nodes.length) {
    nodes.forEach(function(n, i){ n.x = POS[i][0]; n.y = POS[i][1]; });
  } else {
    var nbt = nodes.length - nf;
    nodes.forEach(function(n, i){
      var isTheme = n.type === "theme";
      var k = isTheme ? (i - nf) : i;
      var total = Math.max(1, isTheme ? nbt : nf);
      var a = (k / total) * Math.PI * 2;
      var rad = isTheme ? 160 : 320;
      n.x = Math.cos(a) * rad; n.y = Math.sin(a) * rad;
    });
  }
  var sansTheme = FICHES.filter(function(f){ return !(f.themes || []).length; }).length;
  document.getElementById("stats").textContent = pluriel(nf, "fiche") + " · " + pluriel(THEMES.length, "thème")
    + (sansTheme ? " · " + sansTheme + " sans thème" : "");

  /* ---- toile ---- */
  var canvas = document.getElementById("c");
  var ctx = canvas.getContext("2d");
  document.getElementById("statique").style.display = "none";
  canvas.style.display = "block";
  var dpr = 1, W = 0, H = 0, zoom = 1, panX = 0, panY = 0, survol = null;
  var tokenAnim = 0;   /* annule un retour en cours dès qu'on re-touche */

  function voisins(i){
    var s = [i];
    edges.forEach(function(e){
      if (e.s === i && s.indexOf(e.t) === -1) { s.push(e.t); }
      if (e.t === i && s.indexOf(e.s) === -1) { s.push(e.s); }
    });
    return s;
  }
  function dessiner(){
    if (!W) { return; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = pal.fond;
    ctx.fillRect(0, 0, W, H);
    if (pal.halo) {
      var g = ctx.createRadialGradient(W / 2, -80, 40, W / 2, -80, Math.max(W, 700));
      g.addColorStop(0, pal.halo);
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
    }
    ctx.save();
    ctx.translate(W / 2 + panX, H / 2 + panY);
    ctx.scale(zoom, zoom);
    var foyer = survol === null ? null : voisins(survol);
    edges.forEach(function(e){
      var actif = foyer && foyer.indexOf(e.s) !== -1 && foyer.indexOf(e.t) !== -1;
      ctx.globalAlpha = foyer && !actif ? 0.22 : 1;
      ctx.strokeStyle = actif ? pal.lienFort : pal.lien;
      var a = nodes[e.s], b = nodes[e.t];
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    });
    ctx.globalAlpha = 1;
    nodes.forEach(function(n, i){
      var actif = !foyer || foyer.indexOf(i) !== -1;
      ctx.globalAlpha = actif ? 1 : 0.14;
      var rr = n.r + (survol === i ? 1.5 : 0);
      if (n.type === "theme") {
        ctx.shadowColor = pal.theme;
        ctx.shadowBlur = foyer && actif ? 22 : 13;
        ctx.fillStyle = pal.theme;
        ctx.beginPath(); ctx.arc(n.x, n.y, rr, 0, Math.PI * 2); ctx.fill();
        ctx.shadowBlur = 0;
      } else {
        var col = couleurFiche(n);
        if (n.t !== null && n.t > 0.66) { ctx.shadowColor = col; ctx.shadowBlur = 7; }
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(n.x, n.y, rr, 0, Math.PI * 2); ctx.fill();
        ctx.shadowBlur = 0;
      }
    });
    ctx.textAlign = "center";
    var assez = zoom > 0.5 || nodes.length <= 16;
    nodes.forEach(function(n, i){
      var actif = !foyer || foyer.indexOf(i) !== -1;
      ctx.globalAlpha = actif ? 1 : 0.14;
      if (n.type === "theme") {
        ctx.fillStyle = pal.themeLabel;
        ctx.font = "600 13px -apple-system,sans-serif";
        ctx.fillText(n.label + " · " + n.n, n.x, n.y - n.r - 8);
      } else if (assez || (foyer && foyer.indexOf(i) !== -1)) {
        ctx.fillStyle = pal.ficheLabel;
        ctx.font = "11px -apple-system,sans-serif";
        var t = n.fiche.titre || "";
        if (t.length > 44) { t = t.slice(0, 43) + "…"; }
        ctx.fillText(t, n.x, n.y + n.r + 14);
      }
    });
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  /* ---- caméra ---- */
  function applyZoom(f, cx, cy){
    var nz = Math.min(3, Math.max(0.3, zoom * f));
    if (nz === zoom) { return; }
    var wx = (cx - W / 2 - panX) / zoom, wy = (cy - H / 2 - panY) / zoom;
    zoom = nz;
    panX = cx - W / 2 - wx * zoom;
    panY = cy - H / 2 - wy * zoom;
    dessiner();
  }
  function fitTargets(){
    var minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
    nodes.forEach(function(n){
      minX = Math.min(minX, n.x - n.r); maxX = Math.max(maxX, n.x + n.r);
      minY = Math.min(minY, n.y - n.r - 24); maxY = Math.max(maxY, n.y + n.r + 38);
    });
    var bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
    var tz = Math.min(2.2, Math.max(0.3, Math.min((W - 100) / bw, (H - 190) / bh)));
    return [tz, -((minX + maxX) / 2) * tz, -((minY + maxY) / 2) * tz];
  }
  function fitView(){ var t = fitTargets(); zoom = t[0]; panX = t[1]; panY = t[2]; }
  function toWorld(sx, sy){ return { x: (sx - W / 2 - panX) / zoom, y: (sy - H / 2 - panY) / zoom }; }
  function hit(sx, sy){
    var p = toWorld(sx, sy);
    for (var i = nodes.length - 1; i >= 0; i--) {
      var n = nodes[i], dx = n.x - p.x, dy = n.y - p.y;
      var rr = n.r + (n.type === "theme" ? 12 : 14);
      if (dx * dx + dy * dy < rr * rr) { return i; }
    }
    return null;
  }

  /* ---- le glisser vit : les voisins suivent, puis tout revient en douceur ---- */
  function entrainerVoisins(idx){
    var n = nodes[idx];
    edges.forEach(function(edge){
      var autre = -1;
      if (edge.s === idx) { autre = edge.t; }
      else if (edge.t === idx) { autre = edge.s; }
      if (autre === -1) { return; }
      var o = nodes[autre];
      var dx = o.x - n.x, dy = o.y - n.y;
      var d = Math.max(1, Math.hypot(dx, dy));
      o.x += (n.x + dx / d * 115 - o.x) * 0.22;
      o.y += (n.y + dy / d * 115 - o.y) * 0.22;
    });
  }
  function lancerRetour(sauf){
    if (!POS || POS.length !== nodes.length) { return; }
    var depuis = nodes.map(function(n){ return [n.x, n.y]; });
    var mon = ++tokenAnim;
    var debut = performance.now();
    var duree = 750;
    function pas(maintenant){
      if (mon !== tokenAnim) { return; }
      var k = Math.min(1, (maintenant - debut) / duree);
      var e = 1 - Math.pow(1 - k, 3);
      nodes.forEach(function(n, i){
        if (sauf && sauf[i]) { return; }   /* point « posé » : il reste là */
        n.x = depuis[i][0] + (POS[i][0] - depuis[i][0]) * e;
        n.y = depuis[i][1] + (POS[i][1] - depuis[i][1]) * e;
      });
      dessiner();
      if (k < 1) { requestAnimationFrame(pas); }
    }
    requestAnimationFrame(pas);
  }

  /* ---- aperçu (surimpression) ---- */
  var apercu = document.getElementById("apercu");
  function ouvrirApercu(f){
    document.getElementById("ap-titre").textContent = f.titre || "";
    var meta = [];
    if (f.auteur) { meta.push(f.auteur); }
    if (f.date_fr) { meta.push(f.date_fr); }
    if (f.plateforme) { meta.push(f.plateforme.charAt(0).toUpperCase() + f.plateforme.slice(1)); }
    document.getElementById("ap-meta").textContent = meta.join(" · ");
    document.getElementById("ap-contenu").textContent = f.contenu || "";
    document.getElementById("ap-fiche").href = "vault.html#" + encodeURIComponent(f.id || "");
    var video = document.getElementById("ap-video");
    video.style.display = f.lien ? "" : "none";
    video.href = f.lien || "#";
    var th = document.getElementById("ap-theme");
    if ((f.themes || []).length) {
      th.style.display = "";
      th.href = "vault.html?theme=" + encodeURIComponent(f.themes[0]);
      th.textContent = "Explorer « " + f.themes[0] + " »";
    } else {
      th.style.display = "none";
    }
    apercu.style.display = "block";
  }
  function fermerApercu(){ apercu.style.display = "none"; }
  document.getElementById("fermer").addEventListener("click", fermerApercu);
  document.addEventListener("keydown", function(ev){ if (ev.key === "Escape") { fermerApercu(); } });
  function cliquer(i){
    var n = nodes[i];
    if (n.type === "theme") {
      window.location.href = "vault.html?theme=" + encodeURIComponent(n.label);
      return;
    }
    ouvrirApercu(n.fiche);
  }

  /* ---- interactions ---- */
  var pointers = new Map();
  var dragNode = null, panning = false, pinchPrev = null, downX = 0, downY = 0, bouge = false;
  canvas.addEventListener("pointerdown", function(e){
    fermerApercu();
    tokenAnim++;                    /* annule un éventuel retour en cours */
    try { canvas.setPointerCapture(e.pointerId); } catch (err) {}
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    downX = e.clientX; downY = e.clientY; bouge = false;
    if (pointers.size === 2) { dragNode = null; panning = false; pinchPrev = null; }
    else {
      var i = hit(e.clientX, e.clientY);
      if (i !== null) { dragNode = i; }
      else { panning = true; }
    }
  });
  canvas.addEventListener("pointermove", function(e){
    var prev = pointers.get(e.pointerId);
    if (prev) {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        var pts = []; pointers.forEach(function(v){ pts.push(v); });
        var d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
        var cx = (pts[0].x + pts[1].x) / 2, cy = (pts[0].y + pts[1].y) / 2;
        if (pinchPrev && pinchPrev.d > 0) { applyZoom(d / pinchPrev.d, cx, cy); }
        pinchPrev = { d: d };
        return;
      }
      if (dragNode !== null) {
        var p = toWorld(e.clientX, e.clientY);
        nodes[dragNode].x = p.x; nodes[dragNode].y = p.y;
        entrainerVoisins(dragNode);
        if (Math.hypot(e.clientX - downX, e.clientY - downY) > 8) {
          if (!bouge) { canvas.style.cursor = "grabbing"; }
          bouge = true;
        }
        dessiner();
      } else if (panning) {
        panX += e.clientX - prev.x; panY += e.clientY - prev.y;
        dessiner();
      }
      return;
    }
    var i = hit(e.clientX, e.clientY);
    if (i !== survol) { survol = i; canvas.style.cursor = i === null ? "" : "grab"; dessiner(); }
  });
  function finPointer(e){
    if (!pointers.has(e.pointerId)) { return; }
    pointers.delete(e.pointerId);
    if (dragNode !== null) {
      if (bouge) {
        if (aimant) { lancerRetour(null); }
        else { poses[dragNode] = true; lancerRetour(poses); }
      } else { cliquer(dragNode); }
    }
    if (pointers.size === 0) {
      dragNode = null; panning = false; pinchPrev = null;
      canvas.style.cursor = "";
    }
  }
  canvas.addEventListener("pointerup", finPointer);
  canvas.addEventListener("pointercancel", function(e){
    pointers.delete(e.pointerId);
    if (pointers.size === 0) { dragNode = null; panning = false; pinchPrev = null; }
  });
  canvas.addEventListener("pointerleave", function(){
    if (survol !== null) { survol = null; dessiner(); }
  });
  canvas.addEventListener("wheel", function(e){
    e.preventDefault();
    applyZoom(Math.exp(-e.deltaY * 0.0012), e.clientX, e.clientY);
  }, { passive: false });
  document.getElementById("zi").addEventListener("click", function(){ applyZoom(1.35, W / 2, H / 2); });
  document.getElementById("zo").addEventListener("click", function(){ applyZoom(1 / 1.35, W / 2, H / 2); });

  /* ---- démarrage ---- */
  function resize(){
    dpr = window.devicePixelRatio || 1;
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
  }
  window.addEventListener("resize", function(){ resize(); dessiner(); });
  resize();
  fitView();
  choisirTheme(initial, false);
})();
</script>
</body>
</html>
"""


MOIS_LONGS = ["janvier", "février", "mars", "avril", "mai", "juin",
              "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
               "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def normaliser_lien(lien):
    """Clé de rapprochement fiche ↔ index : la forme canonique du lien.

    Les applis ajoutent des paramètres (?stkn=…, ?si=…) qui changent d'un
    partage à l'autre : on les ignore des deux côtés pour que la bonne fiche
    (et donc la bonne date) soit toujours retrouvée. Pour YouTube, la forme
    canonique garde l'identifiant de la vidéo (« watch?v=… »), sans quoi
    toutes les vidéos « watch » partageraient la même clé.
    """
    return lien_canonique(lien).rstrip("/")


def plateforme_de(lien):
    """Identifie la plateforme d'un lien (pour le petit glyphe des cartes)."""
    l = (lien or "").lower()
    if "youtube.com" in l or "youtu.be" in l:
        return "youtube"
    if "instagram.com" in l:
        return "instagram"
    if "tiktok.com" in l:
        return "tiktok"
    return ""


GLYPHES = {
    "youtube": '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><rect x="2.6" y="5.4" width="18.8" height="13.2" rx="4"/><path d="M10.4 9.4l4.6 2.6-4.6 2.6z" fill="currentColor" stroke="none"/></svg>',
    "instagram": '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.4" cy="6.6" r="1.2" fill="currentColor" stroke="none"/></svg>',
    "tiktok": '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M14.8 4v9.4a3.7 3.7 0 1 1-2.8-3.57"/><path d="M14.8 4c.4 2.3 1.9 3.8 4.1 4"/></svg>',
}


def glyphe_plateforme(cle):
    """Le petit glyphe de plateforme (vide si inconnue)."""
    if cle not in GLYPHES:
        return ""
    return '<span class="pf" aria-hidden="true">' + GLYPHES[cle] + '</span>'


def libelle_mois(date_iso):
    """'2026-10-08' → 'Octobre 2026' (vide si la date manque)."""
    try:
        annee, mois = date_iso.split("-")[0], int(date_iso.split("-")[1])
        return MOIS_LONGS[mois - 1].capitalize() + " " + annee
    except (ValueError, IndexError):
        return ""


def formater_date(date_iso):
    """'2026-10-08' → '8 oct. 2026' (vide si la date manque)."""
    try:
        annee, mois, jour = date_iso.split("-")
        return str(int(jour)) + " " + MOIS_COURTS[int(mois) - 1] + " " + annee
    except (ValueError, IndexError):
        return ""


def canonicaliser_themes(entrees):
    """Fusionne les variantes d'un même thème (« SEO » = « seo ») et nettoie.

    Le libellé retenu est la variante la plus fréquente (à égalité : la
    minuscule), et chaque fiche est dédoublonnée en conséquence. Appliqué aux
    entrées AVANT tout rendu : pastilles, cartes et carte du graphe restent
    ainsi parfaitement cohérents.
    """
    comptes = {}
    for e in entrees:
        for t in e["themes"]:
            propret = t.strip()
            if propret:
                variantes = comptes.setdefault(propret.lower(), {})
                variantes[propret] = variantes.get(propret, 0) + 1
    libelles = {}
    for cle, variantes in comptes.items():
        libelles[cle] = sorted(variantes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    for e in entrees:
        vus = []
        for t in e["themes"]:
            libelle = libelles.get(t.strip().lower())
            if libelle and libelle not in vus:
                vus.append(libelle)
        e["themes"] = vus
    return entrees


def preparer_entrees(entrees, vault):
    """Complète chaque entrée avec sa fiche brute (date, durée, description,
    transcription), puis trie : récentes d'abord."""
    brutes = fiches_brutes(vault)
    for e in entrees:
        e["lien"] = lien_sur(e["lien"])
        brute = brutes.get(normaliser_lien(e["lien"]), {}) if e["lien"] else {}
        e["date"] = brute.get("traite_le", "")
        e["plateforme"] = plateforme_de(e["lien"] or brute.get("source", ""))
        e["date_fr"] = formater_date(e["date"])   # pour l'aperçu de la Carte
        e["duree"] = duree_lisible(brute.get("duree_s"))
        e["description"] = brute.get("description", "")
        e["transcription"] = brute.get("transcription", "")
        e["fichier"] = brute.get("fichier", "")
        e["memo"] = lire_memo(vault, e["fichier"]) if e["fichier"] else None
    entrees.sort(key=lambda e: e["date"] or "", reverse=True)
    return entrees


THEMES_CACHES = {"(en attente)"}      # thème technique des entrées « résumé en attente »
MARQUEUR_ATTENTE = "(résumé en attente"


def section_connue(titre):
    """« Transcription », « Transcription audio » (ancien format), « Description »…
    → « transcription » / « description », ou None pour une autre section."""
    nom = " ".join(titre.strip().lower().split())
    for connue in ("transcription", "description"):
        if nom == connue or nom.startswith(connue + " "):
            return connue
    return None


def lire_fiche_brute(chemin):
    """Une fiche de raw/ → {source, plateforme, auteur, duree_s, traite_le,
    titre, description, transcription}. Seules les sections connues sont lues
    (« Description », « Transcription », y compris l'ancien titre « Transcription
    audio ») : les ajouts d'autres outils sont ignorés."""
    try:
        texte = Path(chemin).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    fiche = {"titre": "", "description": "", "transcription": ""}
    lignes = texte.splitlines()
    corps = lignes
    if lignes and lignes[0].strip() == "---":
        for i, ligne in enumerate(lignes[1:60], 1):
            if ligne.strip() == "---":
                corps = lignes[i + 1:]
                break
            if ":" in ligne:
                cle, valeur = ligne.split(":", 1)
                fiche[cle.strip()] = valeur.strip()
    section = None
    morceaux = {"description": [], "transcription": []}
    for ligne in corps:
        if ligne.startswith("# ") and not fiche["titre"]:
            fiche["titre"] = ligne[2:].strip()
            continue
        if ligne.startswith("## "):
            section = section_connue(ligne[3:])
            continue
        if section:
            morceaux[section].append(ligne)
    for nom, contenu in morceaux.items():
        valeur = "\n".join(contenu).strip()
        if valeur in ("(vide)", "(pas de texte récupéré)"):
            valeur = ""
        fiche[nom] = valeur
    return fiche


def fiches_brutes(vault):
    """{lien canonique: fiche brute} pour toutes les fiches de raw/."""
    resultat = {}
    dossier = Path(vault) / "raw"
    if not dossier.is_dir():
        return resultat
    for chemin in sorted(dossier.glob("*.md")):
        if chemin.name.startswith("."):
            continue
        fiche = lire_fiche_brute(chemin)
        if fiche.get("source"):
            fiche["fichier"] = chemin.stem
            resultat[normaliser_lien(fiche["source"])] = fiche
    return resultat


def paragraphes(texte, phrases_par_paragraphe=3, mots_max=70):
    """Découpe une transcription d'un seul bloc en paragraphes lisibles.

    Avec ponctuation : quelques phrases par paragraphe. Sans ponctuation
    (sous-titres automatiques) : des morceaux d'environ 70 mots."""
    texte = " ".join((texte or "").split())
    if not texte:
        return []
    phrases = re.split(r"(?<=[.!?…])\s+(?=[«\"A-ZÀ-ÖØ-Þ0-9])", texte)
    resultat, courant, nb_mots = [], [], 0
    for phrase in phrases:
        mots = phrase.split()
        # Phrase trop longue (pas de ponctuation) : on la coupe en morceaux.
        while len(mots) > mots_max:
            if courant:
                resultat.append(" ".join(courant))
                courant, nb_mots = [], 0
            resultat.append(" ".join(mots[:mots_max]))
            mots = mots[mots_max:]
        if not mots:
            continue
        courant.append(" ".join(mots))
        nb_mots += len(mots)
        if len(courant) >= phrases_par_paragraphe or nb_mots >= mots_max:
            resultat.append(" ".join(courant))
            courant, nb_mots = [], 0
    if courant:
        resultat.append(" ".join(courant))
    return resultat


def duree_lisible(secondes):
    """« 754.2 » → « 13 min » ; « 42 » → « 42 s » ; vide si inconnue."""
    try:
        s = float(secondes)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    if s < 60:
        return str(int(round(s))) + " s"
    return str(int(round(s / 60))) + " min"


def en_attente(e):
    """Vrai si l'entrée attend encore son résumé."""
    return (e.get("contenu") or "").startswith(MARQUEUR_ATTENTE)


def themes_visibles(e):
    return [t for t in e["themes"] if t not in THEMES_CACHES]


def attribuer_ids(entrees):
    """Un identifiant d'ancre stable et unique par entrée (« f-yt_abc »)."""
    vus = set()
    for e in entrees:
        base = "f-" + (e.get("fichier") or identifiant(e.get("lien") or e["titre"]))
        candidat, n = base, 2
        while candidat in vus:
            candidat, n = base + "-" + str(n), n + 1
        vus.add(candidat)
        e["id"] = candidat
    return entrees


def calculer_lies(entrees, maximum=3):
    """Pour chaque entrée, les vidéos les plus proches (thèmes en commun,
    puis les plus récentes)."""
    for e in entrees:
        mes_themes = set(themes_visibles(e))
        candidats = []
        for autre in entrees:
            if autre is e:
                continue
            communs = len(mes_themes & set(themes_visibles(autre)))
            if communs:
                candidats.append((-communs, autre.get("date") or "", autre))
        # les plus récentes d'abord, puis (tri stable) le plus de thèmes communs
        candidats.sort(key=lambda c: c[1], reverse=True)
        candidats.sort(key=lambda c: c[0])
        e["lies"] = [c[2]["id"] for c in candidats[:maximum]]
    return entrees


def favicon():
    """Petite bobine noire sur fond ambre, encodée en data URI (onglet + écran d'accueil)."""
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
           "<rect width='64' height='64' rx='14' fill='#FEC90A'/>"
           "<circle cx='32' cy='32' r='17' fill='none' stroke='#000000' stroke-width='6'/>"
           "<circle cx='32' cy='32' r='5.5' fill='#000000'/>"
           "<circle cx='32' cy='13.5' r='4' fill='#000000'/>"
           "<circle cx='32' cy='50.5' r='4' fill='#000000'/>"
           "<circle cx='13.5' cy='32' r='4' fill='#000000'/>"
           "<circle cx='50.5' cy='32' r='4' fill='#000000'/>"
           "</svg>")
    return "data:image/svg+xml," + urllib.parse.quote(svg, safe="")


def rendre_chips(entrees):
    """Pastilles de thèmes en HTML statique (triées par fréquence), précédées de « Tout »."""
    comptes = {}
    for e in entrees:
        for t in themes_visibles(e):
            comptes[t] = comptes.get(t, 0) + 1
    if not comptes:
        return ""
    paires = sorted(comptes.items(), key=lambda kv: (-kv[1], kv[0]))
    return ('<button type="button" class="chip on" data-t="" aria-pressed="true">Tout</button>'
            + "".join(
                '<button type="button" class="chip" data-t="' + html.escape(t, quote=True)
                + '" aria-pressed="false">' + html.escape(t)
                + '<span class="n">' + str(n) + '</span></button>'
                for t, n in paires))


def meta_html(e, complete=False):
    date = formater_date(e.get("date", ""))
    morceaux = [glyphe_plateforme(e.get("plateforme", "")) + "<span>" + html.escape(e["auteur"] or "Auteur inconnu") + "</span>"]
    if complete:
        nom = LIBELLES_PLATEFORMES.get(e.get("plateforme", ""))
        if nom:
            morceaux.append("<span>" + nom + "</span>")
        if e.get("duree"):
            morceaux.append("<span>" + html.escape(e["duree"]) + "</span>")
        if date:
            morceaux.append("<span>Enregistrée le " + html.escape(date) + "</span>")
    elif date:
        morceaux.append("<span>" + html.escape(date) + "</span>")
    return '<span class="sep">·</span>'.join(morceaux)


ICONE_HORLOGE = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">'
                 '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>')
ICONE_LECTURE = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">'
                 '<circle cx="12" cy="12" r="9"/><path d="M10 8.5v7l6-3.5z"/></svg>')
ICONE_RETOUR = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">'
                '<path d="M15 18l-6-6 6-6"/></svg>')
ICONE_LOUPE = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">'
               '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>')
LIBELLES_PLATEFORMES = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}


def rendre_carte(e):
    """Une carte de la bibliothèque : un lien vers la fiche complète."""
    attente = en_attente(e)
    resume = "" if attente else e["contenu"]
    memo = e.get("memo") or {}
    extras = memo.get("a_retenir", []) + ([memo["memo"]["idee"]] + memo["memo"]["points"] if memo else [])
    texte_filtre = " ".join([e["titre"], e["auteur"], resume] + themes_visibles(e) + extras)
    corps = ('<span class="pastille attente">' + ICONE_HORLOGE + "Résumé à venir</span>" if attente
             else '<p class="res">' + html.escape(resume) + "</p>")
    return (
        '<a class="carte" href="#' + e["id"] + '" data-fiche="' + e["id"]
        + '" data-themes="' + html.escape("|".join(themes_visibles(e)), quote=True)
        + '" data-text="' + html.escape(texte_filtre, quote=True)
        + '" data-titre="' + html.escape(e["titre"], quote=True)
        + '" data-contenu="' + html.escape(resume, quote=True) + '">'
        + '<span class="meta">' + meta_html(e) + "</span>"
        + '<h2><span class="tt">' + html.escape(e["titre"]) + "</span></h2>"
        + corps
        + "</a>"
    )


def rendre_liste(entrees):
    """Les cartes dans la grille, précédées d'un séparateur de mois (récentes d'abord)."""
    if not entrees:
        return ('<p class="vide">Aucune vidéo pour l\'instant. '
                "Partage une vidéo depuis ton téléphone : elle apparaîtra ici.</p>")
    parties = []
    mois_courant = None
    for e in entrees:
        mois = libelle_mois(e.get("date", "")) or ""
        if mois and mois != mois_courant:
            parties.append('<div class="mois">' + html.escape(mois) + "</div>")
        mois_courant = mois
        parties.append(rendre_carte(e))
    return "".join(parties)


def bloc_a_retenir(memo):
    if not memo or not memo.get("a_retenir"):
        return ""
    return ('<div class="encadre"><div class="encadre-titre">À retenir</div><ol class="retenir">'
            + "".join('<li><span class="num">' + str(i) + "</span><span>" + html.escape(r) + "</span></li>"
                      for i, r in enumerate(memo["a_retenir"], 1))
            + "</ol></div>")


def bloc_pour_toi(memo, profil):
    """« Pour toi » si le profil existe ; sinon, une invitation discrète (seulement
    quand Bobine produit déjà des mémos, donc quand une clé est configurée)."""
    if not memo:
        return ""
    if profil and memo.get("pour_toi"):
        return ('<div class="encadre pourtoi"><div class="encadre-titre">Pour toi'
                '<span class="encadre-sous">d\'après ton profil</span></div><p>'
                + html.escape(memo["pour_toi"]) + "</p></div>")
    if not profil:
        return ('<div class="encadre platine"><div class="encadre-titre">Pour toi</div>'
                '<p>Décris-toi en quelques lignes dans ton <a href="#profil">profil</a>, '
                "et Bobine te dira ce que chaque vidéo t'apporte.</p></div>")
    return ""   # profil tout neuf : « Pour toi » arrive au prochain passage


def rendre_memo(memo):
    m = memo["memo"]
    html_memo = "<h3>L'idée centrale</h3><p>" + html.escape(m["idee"]) + "</p>"
    if m["points"]:
        html_memo += "<h3>Les points clés</h3><ul>" + "".join("<li>" + html.escape(x) + "</li>" for x in m["points"]) + "</ul>"
    if m["etapes"]:
        html_memo += "<h3>Les étapes</h3><ol>" + "".join("<li>" + html.escape(x) + "</li>" for x in m["etapes"]) + "</ol>"
    if m["outils"]:
        html_memo += "<h3>Outils et ressources cités</h3><ul>" + "".join("<li>" + html.escape(x) + "</li>" for x in m["outils"]) + "</ul>"
    return '<div class="lecture memo">' + html_memo + "</div>"


def rendre_fiche(e, par_id, profil=""):
    """La fiche complète d'une vidéo : En bref, Transcription, vidéos liées.
    Lisible sans JavaScript (les deux niveaux s'affichent l'un sous l'autre)."""
    id_ = e["id"]
    attente = en_attente(e)
    paras = paragraphes(e.get("transcription", ""))
    a_transcript = bool(paras)

    if attente:
        bref = ('<div class="encadre"><strong>Résumé à venir</strong>'
                "Ta vidéo est bien enregistrée. Bobine prépare son résumé et réessaiera automatiquement si besoin."
                + (' En attendant, tu peux lire la <a href="#' + id_ + '" data-vers="transcript">transcription complète</a>.'
                   if a_transcript else "")
                + "</div>")
    else:
        bref = ('<div class="lecture"><p>' + html.escape(e["contenu"]) + "</p></div>"
                + bloc_a_retenir(e.get("memo")) + bloc_pour_toi(e.get("memo"), profil))

    if a_transcript:
        transcript = ('<label class="chercher">' + ICONE_LOUPE
                      + '<input type="search" placeholder="Chercher dans la transcription…" '
                        'aria-label="Chercher dans la transcription"><span class="compte"></span></label>'
                      + '<div class="lecture transcript">'
                      + "".join("<p>" + html.escape(p) + "</p>" for p in paras) + "</div>")
    else:
        transcript = ('<div class="encadre"><strong>Pas de transcription</strong>'
                      "Cette vidéo ne contient pas de parole, ou son texte n'a pas pu être récupéré.</div>")
    if e.get("description"):
        transcript += ('<details class="description"><summary>Description publiée avec la vidéo</summary><p>'
                       + html.escape(e["description"]) + "</p></details>")

    memo = e.get("memo")
    niveaux = (
        '<div class="niveaux" role="tablist" aria-label="Niveau de lecture">'
        '<button type="button" class="niveau" role="tab" data-niveau="bref" '
        'data-aide="Pour savoir en 30 secondes si cette vidéo t\'intéresse." aria-selected="true">En bref</button>'
        + ('<button type="button" class="niveau" role="tab" data-niveau="memo" '
           'data-aide="La note complète, organisée pour être relue." aria-selected="false">Mémo</button>' if memo else "")
        + '<button type="button" class="niveau" role="tab" data-niveau="transcript" '
        'data-aide="Tout ce qui est dit dans la vidéo, mot pour mot." aria-selected="false">Transcription</button>'
        '</div><p class="aide"></p>'
    )
    section_memo = ('<section class="section-niveau" data-niveau="memo"><h2 class="titre-niveau">Mémo</h2>'
                    + rendre_memo(memo) + "</section>") if memo else ""
    lien = lien_sur(e.get("lien", ""))
    bouton = ('<a class="btn" href="' + html.escape(lien, quote=True)
              + '" target="_blank" rel="noopener noreferrer">' + ICONE_LECTURE + "Voir la vidéo</a>") if lien else ""
    lies = [par_id[i] for i in e.get("lies", []) if i in par_id]
    bloc_lies = ""
    if lies:
        bloc_lies = ('<div class="cote-bloc"><h3>Dans ta bibliothèque</h3>'
                     + "".join('<a class="lie" href="#' + l["id"] + '"><strong>' + html.escape(l["titre"])
                               + "</strong><span>" + html.escape(l["auteur"] or "")
                               + (" · " + html.escape(formater_date(l.get("date", ""))) if l.get("date") else "")
                               + "</span></a>" for l in lies)
                     + "</div>")
    themes = themes_visibles(e)
    bloc_themes = ""
    if themes:
        bloc_themes = ('<div class="cote-bloc"><h3>Thèmes</h3><div class="themes-fiche">'
                       + "".join('<a class="pastille" href="#bibliotheque" data-filtre="'
                                 + html.escape(t, quote=True) + '">' + html.escape(t) + "</a>" for t in themes)
                       + "</div></div>")
    return (
        '<article class="fiche" id="' + id_ + '" aria-labelledby="t-' + id_ + '">'
        + '<a class="retour" href="#bibliotheque">' + ICONE_RETOUR + "Bibliothèque</a>"
        + '<div class="fiche-grille"><div>'
        + '<h1 id="t-' + id_ + '">' + html.escape(e["titre"]) + "</h1>"
        + '<div class="meta">' + meta_html(e, complete=True) + "</div>"
        + bouton
        + '<a class="btn demander-acces" href="#demander" data-demander-fiche="'
        + html.escape(id_, quote=True) + '" hidden>Poser une question sur cette vidéo</a>'
        + niveaux
        + '<section class="section-niveau" data-niveau="bref"><h2 class="titre-niveau">En bref</h2>' + bref + "</section>"
        + section_memo
        + '<section class="section-niveau" data-niveau="transcript"><h2 class="titre-niveau">Transcription</h2>'
        + transcript + "</section>"
        + "</div>"
        + '<aside class="cote">' + bloc_lies + bloc_themes + "</aside>"
        + "</div></article>"
    )


def rendre_fiches(entrees, profil=""):
    par_id = {e["id"]: e for e in entrees}
    return "\n".join(rendre_fiche(e, par_id, profil) for e in entrees)


def rendre_profil(profil, chemin=FICHIER_PROFIL):
    """La page Profil : le texte actuel, à quoi il sert, comment le changer."""
    if profil:
        actuel = ('<div class="encadre platine"><div class="encadre-titre">Ce que Bobine sait de toi</div>'
                  '<p class="profil-texte">' + html.escape(profil) + "</p></div>")
    else:
        actuel = ('<div class="encadre platine"><div class="encadre-titre">Pas encore de profil</div>'
                  "<p>C'est facultatif : tout fonctionne sans. Avec quelques lignes sur toi, chaque fiche "
                  "gagne un bloc « Pour toi » qui dit ce que la vidéo t'apporte.</p></div>")
    nom = html.escape(FICHIER_PROFIL)
    return (
        '<section class="vue-profil" id="profil" aria-label="Profil">'
        '<a class="retour" href="#bibliotheque">' + ICONE_RETOUR + "Bibliothèque</a>"
        '<h1 class="titre">Ton profil</h1>'
        '<p class="sous">Quelques lignes suffisent : ce que tu fais, ce qui t\'intéresse, ce que tu cherches dans tes vidéos.</p>'
        '<div class="lecture" style="margin-top:24px">' + actuel
        + '<div class="encadre"><div class="encadre-titre">Pour le modifier</div><p>'
        "Ouvre le fichier « " + nom + " » dans ton dossier Bobine, écris ou change quelques lignes, "
        "puis enregistre. Bobine met à jour les blocs « Pour toi » au fil des prochains passages.</p>"
        '<details class="description"><summary>Bobine tourne sur un serveur ?</summary>'
        "<p>Connecte-toi au serveur, puis ouvre le fichier avec un éditeur de texte :<br>"
        "<code>nano " + html.escape(shlex.quote(str(chemin))) + "</code></p></details></div>"
        '<p class="aide" style="margin-top:18px">Ton profil est envoyé à ton service d\'IA avec les demandes de '
        "résumé, comme le texte des vidéos. Évite d'y mettre des informations sensibles.</p>"
        "</div></section>"
    )


def svg_statique(entrees, pos):
    """Carte du graphe en SVG statique : visible même sans JavaScript (aperçu
    Fichiers/iOS) ; le canvas interactif la remplace quand JS tourne."""
    nb_fiches = len(entrees)
    theme_idx, aretes = {}, []
    for i, e in enumerate(entrees):
        for t in e["themes"]:
            if t not in theme_idx:
                theme_idx[t] = nb_fiches + len(theme_idx)
            aretes.append((i, theme_idx[t]))
    xs = [p[0] for p in pos]
    ys = [p[1] for p in pos]
    minx, maxx = min(xs) - 70, max(xs) + 70
    miny, maxy = min(ys) - 90, max(ys) + 90
    parties = []
    for s0, t0 in aretes:
        x1, y1 = pos[s0]
        x2, y2 = pos[t0]
        parties.append('<line x1="' + str(x1) + '" y1="' + str(y1) + '" x2="'
                       + str(x2) + '" y2="' + str(y2)
                       + '" stroke="rgba(255,255,255,0.18)" stroke-width="1.5"/>')
    for i, e in enumerate(entrees):
        x, y = pos[i]
        parties.append('<a href="vault.html#' + html.escape(e.get("id", ""), quote=True)
                       + '"><circle cx="' + str(x) + '" cy="'
                       + str(y) + '" r="10" fill="#F3F4F6"/></a>')
    for t, j in theme_idx.items():
        x, y = pos[j]
        parties.append('<circle cx="' + str(x) + '" cy="' + str(y)
                       + '" r="20" fill="#FEC90A"/>')
        parties.append('<text x="' + str(x) + '" y="' + str(y - 30)
                       + '" fill="#FFFFFF" font-size="26" font-weight="600" '
                       'text-anchor="middle" '
                       'font-family="-apple-system,sans-serif">'
                       + html.escape(t) + '</text>')
    return ('<svg id="statique" xmlns="http://www.w3.org/2000/svg" viewBox="'
            + str(int(minx)) + ' ' + str(int(miny)) + ' '
            + str(int(maxx - minx)) + ' ' + str(int(maxy - miny))
            + '" preserveAspectRatio="xMidYMid meet">'
            + "".join(parties) + '</svg>')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(VAULT))
    args = ap.parse_args()
    vault = Path(args.vault)

    cfg = lire_config(Path(__file__).resolve().parent, vault)
    nom = cfg.get("NOM") or NOM_DEFAUT
    nom_html = html.escape(nom)
    carte = cfg.get("CARTE", "oui").strip().lower() not in ("non", "no", "n", "0", "false")
    sync_icloud = cfg.get("SYNC_ICLOUD", "oui").strip().lower() not in ("non", "no", "n", "0", "false")
    icloud = Path.home() / "Library/Mobile Documents" / ("com~apple~CloudDocs/" + nom)

    profil = lire_profil(vault)
    entrees = lire_index(vault / "index.md")
    entrees = preparer_entrees(entrees, vault)   # dates (via raw/), plateforme, tri récentes d'abord
    entrees = canonicaliser_themes(entrees)      # fusionne « SEO »/« seo », dédoublonne
    entrees = attribuer_ids(entrees)             # ancre de la fiche complète (« #f-… »)
    entrees = calculer_lies(entrees)             # « Dans ta bibliothèque »
    # La carte n'a besoin que de l'essentiel (jamais les transcriptions).
    pour_carte = [{"id": e["id"], "titre": e["titre"], "lien": e["lien"], "auteur": e["auteur"],
                   "themes": themes_visibles(e), "contenu": "" if en_attente(e) else e["contenu"],
                   "date": e["date"], "date_fr": e["date_fr"], "plateforme": e["plateforme"]}
                  for e in entrees]
    donnees = json.dumps(pour_carte, ensure_ascii=False).replace("<", "\\u003c")

    lien_carte = '<a class="lien-carte" href="graph.html">Carte des thèmes</a>'
    lien_carte_mobile = '<a class="lien-carte-mobile" href="graph.html">Voir la carte des thèmes</a>'
    # Le nom et le lien « Carte » se règlent sur le MODÈLE, avant d'insérer les
    # fiches : le contenu des fiches n'est ainsi jamais modifié par erreur.
    modele_liste = TEMPLATE_LISTE.replace("Vault · mes vidéos sauvegardées",
                                          nom_html + " · mes vidéos sauvegardées")
    if not carte:
        modele_liste = modele_liste.replace(lien_carte, "").replace(lien_carte_mobile, "")
    valeurs_liste = {
        "__FAVICON__": favicon(),
        "__GROUPES__": rendre_liste(entrees),
        "__CHIPS__": rendre_chips(entrees),
        "__STATS__": str(len(entrees)) + " / " + str(len(entrees)),
        "__DATE__": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "__COUNT__": pluriel(len(entrees), "vidéo"),
        "__COMPTE__": pluriel(len(entrees), "vidéo") + (" enregistrée" if len(entrees) < 2 else " enregistrées"),
        "__FICHES__": rendre_fiches(entrees, profil),
        "__PROFIL__": rendre_profil(profil, vault / FICHIER_PROFIL),
    }
    page = remplir(modele_liste, valeurs_liste)
    ecrire_atomique(vault / "vault.html", page)
    print(f"vault.html généré — {pluriel(len(entrees), 'fiche')}")

    if carte and entrees:
        pos = positions_initiales(pour_carte)
        vus_themes = {}
        for e in pour_carte:
            for t in e["themes"]:
                vus_themes[t] = vus_themes.get(t, 0) + 1
        themes_graphe = [{"nom": t, "n": n} for t, n in vus_themes.items()]
        nb_themes = len(themes_graphe)
        modele_graphe = TEMPLATE_GRAPHE.replace("Vault · carte des thèmes", nom_html + " · carte des thèmes")
        graphe = remplir(modele_graphe, {
            "__FAVICON__": favicon(),
            "__ENTREES__": donnees,
            "__POS__": json.dumps(pos),
            "__THEMES__": json.dumps(themes_graphe, ensure_ascii=False).replace("<", "\\u003c"),
            "__SVG__": svg_statique(pour_carte, pos),
            "__STATS_G__": pluriel(len(entrees), "fiche") + " · " + pluriel(nb_themes, "thème"),
        })
        ecrire_atomique(vault / "graph.html", graphe)
        print("graph.html généré — la carte du graphe")
    elif not carte:
        print("carte désactivée (CARTE=non dans config.env)")

    # Copie iCloud (pour l'iPhone) : uniquement vault.html (fiches complètes et
    # transcriptions comprises, tout tient dans ce fichier), et seulement quand
    # on génère bien le Vault principal (= le dossier de ce script). Le graph
    # reste sur le Mac (décision utilisateur : pas besoin sur l'iPhone).
    if sys.platform != "darwin":
        print("copie iCloud ignorée (macOS uniquement).")
    elif not sync_icloud:
        print("copie iCloud désactivée (SYNC_ICLOUD=non dans config.env).")
    elif vault.resolve() == Path(__file__).resolve().parent:
        try:
            icloud.mkdir(parents=True, exist_ok=True)
            ecrire_atomique(icloud / "vault.html", page.replace(lien_carte, "").replace(lien_carte_mobile, ""))
            print(f"copie iCloud : {icloud} (vault.html seulement)")
        except OSError as e:
            print(f"copie iCloud impossible : {e}")
    else:
        print("vault différent du dossier du script — pas de copie iCloud (test ou usage local).")


if __name__ == "__main__":
    main()
