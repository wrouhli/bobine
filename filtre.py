#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""filtre.py — choisis quoi ingérer, AVANT de lancer la transcription.

Un export Instagram contient tout : astuces, mèmes, citations. Lancer
`ingest.py` sur l'ensemble, c'est des heures de calcul pour des fiches
jamais relues. filtre.py lit l'export, applique tes règles (`filtres.yaml`
— ton fichier personnel, jamais versionné), et écrit la liste des liens
retenus — que `ingest.py` consomme ensuite.

Le rangement de tes collections fait foi : l'export relie chaque post à sa
collection, et filtre.py s'en sert en priorité (le tri est exact, pas
deviné). Les mots-clés (`themes`) ne servent qu'aux posts sans collection.

Parcours :

    python filtre.py --export "…/instagram-mon_compte" --init-config
    #  → écrit filtres.yaml ; ouvre-le, passe à false ce que tu ne veux pas
    python filtre.py --export "…/instagram-mon_compte" --rapport
    #  → compteurs + exemples, pour vérifier avant de lancer
    python filtre.py --export "…/instagram-mon_compte"
    #  → écrit liens-filtres.txt
    python ingest.py liens-filtres.txt

Tout est local : aucune connexion, et aucune dépendance à installer.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

CONFIG_DEFAUT = Path(__file__).with_name("filtres.yaml")
SORTIE_DEFAUT = "liens-filtres.txt"

# Clés de champs de l'export Instagram (la « Légende » arrive parfois
# double-encodée : « LÃ©gende » est le même mot en UTF-8 relu en latin-1).
CHAMP_LIBELLE = ("Légende", "LÃ©gende")

CLASSEMENTS = ("revoir", "garder", "ecarter")


class ErreurFiltre(Exception):
    """Une erreur expliquée à l'utilisateur (le programme s'arrête proprement)."""


# ------------------------------------------------------------------ outils

def reparer_encodage(valeur):
    """L'export Instagram double-encode parfois l'UTF-8 : « cafÃ© » → « café »."""
    if not isinstance(valeur, str):
        return "" if valeur is None else str(valeur)
    try:
        return valeur.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return valeur


def normaliser_url(url):
    """Clé de comparaison d'URL : sans query ni fragment ni « / » final."""
    return str(url).strip().split("?")[0].split("#")[0].rstrip("/")


def normaliser_nom(nom):
    """Clé de comparaison de collection : insensible aux accents, emojis, casse.

    « 💡| Astuces » == « astuces » == « Astuces ! ».
    """
    texte = unicodedata.normalize("NFKD", str(nom).lower())
    texte = texte.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^0-9a-z]+", "", texte)


def _guillemeter(texte):
    """Met un nom entre guillemets pour filtres.yaml (gère apostrophes et guillemets)."""
    texte = str(texte)
    if '"' not in texte:
        return '"%s"' % texte
    if "'" not in texte:
        return "'%s'" % texte
    return '"%s"' % texte.replace('"', "’")


# ------------------------------------------------------- lecture de l'export

def localiser_export(chemin):
    """Trouve saved_posts.json / saved_collections.json, même imbriqués.

    Retourne (dossier_de_l'export, chemin_posts, chemin_collections).
    """
    chemin = Path(str(chemin)).expanduser()
    if chemin.is_file():
        chemin = chemin.parent
    if not chemin.is_dir():
        raise ErreurFiltre("export introuvable : %s" % chemin)

    candidats = sorted(chemin.rglob("saved_posts.json")) or \
        sorted(chemin.rglob("posts.json"))
    if not candidats:
        raise ErreurFiltre(
            "aucun « saved_posts.json » trouvé dans %s\n"
            "  → indique le dossier de l'export Instagram décompressé" % chemin)
    chemin_posts = candidats[0]
    dossier = chemin_posts.parent

    chemin_collections = dossier / "saved_collections.json"
    if not chemin_collections.exists():
        ailleurs = sorted(chemin.rglob("saved_collections.json"))
        if ailleurs:
            chemin_collections = ailleurs[0]
    return dossier, chemin_posts, chemin_collections


def _champs(entree):
    """Transforme une entrée d'export en dictionnaire {label: valeur}."""
    champs = {}
    for element in entree.get("label_values") or []:
        if isinstance(element, dict) and element.get("label") is not None:
            champs[str(element["label"])] = element.get("value")
    return champs


def charger_posts(chemin):
    """Posts sauvegardés : URL, légende, hashtags. Dédupliqués par URL."""
    try:
        donnees = json.loads(Path(chemin).read_text(encoding="utf-8",
                                                    errors="ignore"))
    except ValueError as erreur:
        raise ErreurFiltre("illisible : %s (%s)" % (chemin, erreur))
    if isinstance(donnees, dict):
        donnees = donnees.get("saved_posts") or donnees.get("posts") or []

    posts, vues = [], set()
    for entree in donnees:
        if isinstance(entree, str):                      # liste d'URL simple
            url, legende = entree, ""
        elif isinstance(entree, dict) and entree.get("label_values"):
            champs = _champs(entree)
            url = champs.get("URL") or ""
            legende = ""
            for nom in CHAMP_LIBELLE:
                if champs.get(nom):
                    legende = champs[nom]
                    break
        elif isinstance(entree, dict):                   # export simplifié
            url = entree.get("url") or entree.get("link") or ""
            legende = (entree.get("caption") or entree.get("description")
                       or entree.get("title") or "")
        else:
            continue
        url = reparer_encodage(url).strip()
        if not url.startswith("http"):
            continue
        cle = normaliser_url(url)
        if cle in vues:
            continue
        vues.add(cle)
        legende = reparer_encodage(legende)
        posts.append({
            "url": str(url),
            "legende": legende,
            "hashtags": [t.lower() for t in re.findall(r"#(\w+)", legende)],
            "texte": legende.lower(),
        })
    return posts


def medias_collection(entree):
    """URLs des posts rangés dans une collection.

    Piège de l'export Instagram : la liste des posts n'est pas dans une clé
    nommée — elle se cache dans une entrée `label_values` sans libellé,
    où chaque dict imbriqué porte un champ « URL ».
    """
    urls = []
    for element in entree.get("label_values") or []:
        if not isinstance(element, dict):
            continue
        for media in element.get("dict") or []:
            if not isinstance(media, dict):
                continue
            for champ in media.get("dict") or []:
                if (isinstance(champ, dict) and champ.get("label") == "URL"
                        and champ.get("value")):
                    urls.append(str(champ["value"]))
        for lien in element.get("media") or []:          # variantes, au cas où
            if isinstance(lien, str):
                urls.append(lien)
    for lien in entree.get("media") or []:
        if isinstance(lien, str):
            urls.append(lien)
    return urls


def charger_collections(chemin):
    """Collections de l'export : liste [{nom, medias}] + index URL → nom."""
    chemin = Path(chemin)
    if not chemin.exists():
        return [], {}
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8",
                                              errors="ignore"))
    except ValueError:
        return [], {}
    if isinstance(donnees, dict):
        donnees = donnees.get("saved_collections") or []

    collections, index = [], {}
    for entree in donnees:
        if not isinstance(entree, dict):
            continue
        champs = _champs(entree)
        nom = reparer_encodage(champs.get("Nom") or champs.get("Name") or "")
        urls = medias_collection(entree)
        collections.append({"nom": str(nom), "medias": urls})
        for lien in urls:
            index[normaliser_url(lien)] = str(nom)
    return collections, index


# ------------------------------------------------------- filtres.yaml (lecture)

def _retirer_commentaire(ligne):
    """Coupe un commentaire « # … » (hors guillemets, et précédé d'un espace)."""
    guillemet = None
    for i, caractere in enumerate(ligne):
        if guillemet:
            if caractere == guillemet:
                guillemet = None
        elif caractere in "\"'":
            guillemet = caractere
        elif caractere == "#" and (i == 0 or ligne[i - 1] in " \t"):
            return ligne[:i]
    return ligne


def _couper_cle(texte):
    """« clef: valeur » → (clef, valeur). Le « : » doit être suivi d'une
    espace (ou fin de ligne) — ça évite de lire « https://… » comme une clef."""
    guillemet = None
    for i, caractere in enumerate(texte):
        if guillemet:
            if caractere == guillemet:
                guillemet = None
        elif caractere in "\"'":
            guillemet = caractere
        elif caractere == ":" and (i + 1 == len(texte) or texte[i + 1] in " \t"):
            return texte[:i].strip(), texte[i + 1:].strip()
    return None


def _valeur_simple(texte):
    """Retire les guillemets d'une valeur (« Cuisine », 'Cuisine' → Cuisine)."""
    texte = texte.strip()
    if len(texte) >= 2 and texte[0] == texte[-1] and texte[0] in "\"'":
        return texte[1:-1]
    return texte


def _liste_inline(texte):
    """« [a, b, "c, d"] » → ["a", "b", "c, d"] (virgules hors guillemets)."""
    interieur = texte.strip()[1:-1].strip()
    if not interieur:
        return []
    elements, courant, guillemet = [], "", None
    for caractere in interieur:
        if guillemet:
            courant += caractere
            if caractere == guillemet:
                guillemet = None
        elif caractere in "\"'":
            guillemet = caractere
            courant += caractere
        elif caractere == ",":
            elements.append(_valeur_simple(courant))
            courant = ""
        else:
            courant += caractere
    elements.append(_valeur_simple(courant))
    return [e for e in elements if e != ""]


def _valeur_inline(texte):
    if texte.startswith("[") and texte.endswith("]"):
        return _liste_inline(texte)
    return _valeur_simple(texte)


def _preparer_lignes(texte):
    """[(indentation, contenu, numéro)] — vides et commentaires retirés."""
    lignes = []
    for numero, brute in enumerate(texte.replace("\r\n", "\n").replace("\r", "\n")
                                        .split("\n"), 1):
        reste = brute.lstrip(" \t")
        indentation = len(brute) - len(reste)
        if not reste or reste.startswith("#"):
            continue
        if "\t" in brute[:indentation]:
            raise ErreurFiltre("ligne %d : utilise des espaces, pas des "
                               "tabulations" % numero)
        contenu = _retirer_commentaire(reste).rstrip()
        if contenu:
            lignes.append((indentation, contenu, numero))
    return lignes


def _analyser_liste(lignes, depart, indentation):
    elements, i = [], depart
    while i < len(lignes):
        indent, contenu, numero = lignes[i]
        if indent < indentation:
            break
        if indent > indentation or not contenu.startswith("- "):
            raise ErreurFiltre("ligne %d : attends « - … » (élément de liste)"
                               % numero)
        reste = contenu[2:].strip()
        if not reste:
            raise ErreurFiltre("ligne %d : rien après « - »" % numero)
        couple = _couper_cle(reste)
        if couple is not None:                           # élément = « clef: … »
            clef, valeur = couple
            element = {}
            if valeur:
                element[clef] = _valeur_inline(valeur)
                i += 1
            else:
                if i + 1 < len(lignes) and lignes[i + 1][0] > indentation:
                    element[clef], i = _analyser_bloc(lignes, i + 1,
                                                      lignes[i + 1][0])
                else:
                    element[clef] = None
                    i += 1
            if i < len(lignes) and lignes[i][0] > indentation:
                suite, i = _analyser_mapping(lignes, i, lignes[i][0])
                element.update(suite)
            elements.append(element)
        else:
            elements.append(_valeur_simple(reste))
            i += 1
    return elements, i


def _analyser_mapping(lignes, depart, indentation):
    resultat, i = {}, depart
    while i < len(lignes):
        indent, contenu, numero = lignes[i]
        if indent < indentation:
            break
        if indent > indentation:
            raise ErreurFiltre("ligne %d : indentation inattendue" % numero)
        if contenu.startswith("- "):
            raise ErreurFiltre("ligne %d : liste inattendue ici" % numero)
        couple = _couper_cle(contenu)
        if couple is None:
            raise ErreurFiltre("ligne %d : attends « clef: valeur » (reçu "
                               "« %s »)" % (numero, contenu[:40]))
        clef, reste = couple
        if not clef:
            raise ErreurFiltre("ligne %d : clef vide" % numero)
        if clef in resultat:
            raise ErreurFiltre("ligne %d : « %s » apparaît deux fois"
                               % (numero, clef))
        if reste:
            resultat[clef] = _valeur_inline(reste)
            i += 1
        elif i + 1 < len(lignes) and lignes[i + 1][0] > indentation:
            resultat[clef], i = _analyser_bloc(lignes, i + 1, lignes[i + 1][0])
        else:
            resultat[clef] = None
            i += 1
    return resultat, i


def _analyser_bloc(lignes, depart, indentation):
    if lignes[depart][1].startswith("- "):
        return _analyser_liste(lignes, depart, indentation)
    return _analyser_mapping(lignes, depart, indentation)


def _analyser_texte(texte):
    """Analyse le sous-ensemble YAML de filtres.yaml → structure brute."""
    lignes = _preparer_lignes(texte)
    if not lignes:
        return {}
    if lignes[0][0] != 0:
        raise ErreurFiltre("ligne %d : le fichier doit commencer sans "
                           "indentation" % lignes[0][2])
    structure, suivant = _analyser_mapping(lignes, 0, 0)
    if suivant != len(lignes):
        raise ErreurFiltre("ligne %d : indentation inattendue"
                           % lignes[suivant][2])
    return structure


def _booleen(valeur, contexte):
    if isinstance(valeur, bool):
        return valeur
    texte = str(valeur).strip().lower()
    if texte in ("true", "oui"):
        return True
    if texte in ("false", "non"):
        return False
    raise ErreurFiltre("%s : attends true ou false (reçu « %s »)"
                       % (contexte, valeur))


def valider_config(brut):
    """Structure brute → règles typées + avertissements (jamais d'erreur muette)."""
    if brut is None:
        brut = {}
    if not isinstance(brut, dict):
        raise ErreurFiltre("le fichier doit commencer par des « clef: valeur »")
    connues = ("defaut", "exclusions", "collections", "themes")
    for clef in brut:
        if clef not in connues:
            raise ErreurFiltre("clef inconnue : « %s » (attendu : %s)"
                               % (clef, ", ".join(connues)))
    avertissements = []

    defaut = brut.get("defaut") or "revoir"
    defaut = str(defaut).strip().lower()
    if defaut not in CLASSEMENTS:
        raise ErreurFiltre("defaut : « %s » (attendu : revoir, garder ou "
                           "ecarter)" % defaut)

    exclusions = brut.get("exclusions") or []
    if not isinstance(exclusions, list):
        raise ErreurFiltre("exclusions : une liste attendue — ex. [pub, promo]")

    collections = brut.get("collections") or []
    if not isinstance(collections, list):
        raise ErreurFiltre("collections : une liste d'entrées « - nom: … »")
    collections_propres = []
    for entree in collections:
        if isinstance(entree, str):
            collections_propres.append({"nom": entree.strip(),
                                        "garder": True})
            continue
        if not isinstance(entree, dict) or not entree.get("nom"):
            raise ErreurFiltre("collections : chaque entrée doit avoir un "
                               "« nom »")
        for clef in entree:
            if clef not in ("nom", "garder"):
                avertissements.append("collection « %s » : réglage inconnu "
                                      "« %s » ignoré" % (entree["nom"], clef))
        collections_propres.append({
            "nom": str(entree["nom"]).strip(),
            "garder": _booleen(entree.get("garder", True),
                               "collection « %s » / garder" % entree["nom"]),
        })

    themes = brut.get("themes") or {}
    if not isinstance(themes, dict):
        raise ErreurFiltre("themes : des entrées « nom: » attendues")
    themes_propres = {}
    for nom, regle in themes.items():
        if regle is None:
            regle = {}
        if not isinstance(regle, dict):
            raise ErreurFiltre("themes / %s : attends « garder: » et "
                               "« mots_cles: »" % nom)
        for clef in regle:
            if clef not in ("garder", "mots_cles"):
                avertissements.append("thème « %s » : réglage inconnu "
                                      "« %s » ignoré" % (nom, clef))
        mots = regle.get("mots_cles") or []
        if not isinstance(mots, list):
            raise ErreurFiltre("themes / %s / mots_cles : une liste attendue — "
                               "ex. [astuce, astuces]" % nom)
        mots_propres = [str(m).strip() for m in mots if str(m).strip()]
        if not mots_propres:
            avertissements.append("thème « %s » : aucun mot-clé — il ne "
                                  "servira à rien" % nom)
        themes_propres[nom] = {
            "garder": _booleen(regle.get("garder", True),
                               "thème « %s » / garder" % nom),
            "mots_cles": mots_propres,
        }

    return {
        "defaut": defaut,
        "exclusions": [str(m).strip() for m in exclusions if str(m).strip()],
        "collections": collections_propres,
        "themes": themes_propres,
    }, avertissements


def analyser_config(texte):
    """Texte de filtres.yaml → (règles typées, avertissements)."""
    return valider_config(_analyser_texte(texte))


def charger_config(chemin):
    chemin = Path(chemin)
    if not chemin.exists():
        raise ErreurFiltre(
            "fichier de règles introuvable : %s\n"
            "  → génère-le : python filtre.py --export \"…\" --init-config"
            % chemin)
    try:
        return analyser_config(chemin.read_text(encoding="utf-8",
                                                errors="ignore"))
    except ErreurFiltre as erreur:
        raise ErreurFiltre("%s → %s" % (chemin.name, erreur))


# ------------------------------------------------------------------ règles

def table_collections(regles):
    """nom de collection (normalisé) → garder (bool)."""
    return {normaliser_nom(e["nom"]): e["garder"] for e in regles["collections"]}


def correspond(post, mot):
    """Mot-clé présent ? Hashtag à l'identique, ou mot entier (≥ 5 lettres).

    Le seuil évite les faux positifs des mots courts : un test de sous-chaîne
    ferait matcher « ai » dans « frais » ou « airbnb ».
    """
    mot = str(mot).strip().lower().lstrip("#")
    if not mot:
        return False
    if mot in post["hashtags"]:
        return True
    if len(mot) >= 5:
        motif = r"(?<![\w-])" + re.escape(mot) + r"(?![\w-])"
        return re.search(motif, post["texte"]) is not None
    return False


def classer(post, regles, table, index_collections):
    """Rend (verdict, motif) — verdict dans garder / ecarter / revoir."""
    if any(correspond(post, mot) for mot in regles["exclusions"]):
        return "ecarter", "exclusion"

    # 1. La collection fait foi : c'est TON rangement, pas une déduction.
    collection = index_collections.get(normaliser_url(post["url"]))
    if collection:
        cle = normaliser_nom(collection)
        if cle not in table:
            return "revoir", "collection hors config « %s »" % collection
        if table[cle]:
            return "garder", "collection « %s »" % collection
        return "ecarter", "collection « %s »" % collection

    # 2. Mots-clés (posts sans collection seulement) : le rejet gagne.
    for nom, regle in regles["themes"].items():
        if (regle["garder"] is False
                and any(correspond(post, m) for m in regle["mots_cles"])):
            return "ecarter", "thème « %s »" % nom
    for nom, regle in regles["themes"].items():
        if regle["garder"] is not True:
            continue
        if any(correspond(post, m) for m in regle["mots_cles"]):
            return "garder", "thème « %s »" % nom

    return "revoir", "non classé"


def deja_ingere(journal, url):
    """Ce lien a-t-il déjà une fiche (statut ok), sous l'une de ses formes ?"""
    for cle in (url, url.split("?")[0], normaliser_url(url)):
        entree = journal.get(cle)
        if isinstance(entree, dict) and entree.get("statut") == "ok":
            return True
    return False


def charger_journal(chemin):
    """Journal du vault (pour ne pas refaire l'existant). {} si absent."""
    if not chemin:
        auto = Path(__file__).with_name("journal.json")
        chemin = auto if auto.exists() else None
    if not chemin:
        return {}
    chemin = Path(chemin)
    if not chemin.exists():
        return {}
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8",
                                              errors="ignore"))
    except ValueError:
        return {}
    return donnees if isinstance(donnees, dict) else {}


# ------------------------------------------------------------------ écriture

def ecrire_config_initiale(collections, chemin, export="…"):
    """Écrit un filtres.yaml de départ, pré-rempli avec les collections réelles."""
    entete = """\
# =====================================================================
#  filtres.yaml — ce qui entre dans ton vault, et ce qui n'y entre pas.
# =====================================================================
#
# Généré depuis TON export : les collections ci-dessous sont les tiennes.
# « garder: true »  → elle entre dans le vault
# « garder: false » → elle reste dehors (mèmes, pubs, citations…)
#
# Pour voir l'effet de tes choix, sans rien lancer :
#     python filtre.py --export "%s" --rapport
#
# `defaut` : le sort des posts qu'aucune règle ne classe.
#     revoir  → ni ingérés, ni perdus : listés dans le rapport (conseillé)
#     garder  → tout est ingéré
#     ecarter → ignorés
#
# `themes` (tout en bas) : filet de secours pour les posts sans collection.
# Des mots-clés — mot entier dans la légende ; pour les mots de moins de
# 5 lettres, uniquement en #hashtag exact. Le rejet gagne toujours.
#
# Ce fichier reste chez toi : il n'est jamais publié (voir .gitignore).

defaut: revoir

exclusions: []

collections:
""" % export
    lignes = [entete]
    for entree in sorted(collections, key=lambda c: str(c["nom"]).lower()):
        lignes.append("  - nom: %s\n    garder: true\n"
                      % _guillemeter(entree["nom"]))
    lignes.append("""
themes:
  # Exemple — décommente et adapte si tu veux :
  # astuces:
  #   garder: true
  #   mots_cles: [astuce, astuces, tips]
  # memes:
  #   garder: false
  #   mots_cles: [meme, memes, humour]
""")
    Path(chemin).write_text("".join(lignes), encoding="utf-8")


# ------------------------------------------------------------------ programme

def _afficher_liste_collections(collections, index, regles, table,
                                chemin_collections):
    print("%d collection(s) dans %s"
          % (len(collections), chemin_collections.name))
    print("posts reliés à une collection par l'export : %d"
          % len(index))
    print()
    for entree in sorted(collections, key=lambda c: str(c["nom"]).lower()):
        cle = normaliser_nom(entree["nom"])
        if cle not in table:
            etat = "HORS CONFIG"
        elif table[cle]:
            etat = "GARDER    "
        else:
            etat = "ÉCARTER   "
        print("  [%s] %4d post(s)  %s"
              % (etat, len(entree["medias"]), entree["nom"]))
    manquantes = [e["nom"] for e in regles["collections"]
                  if normaliser_nom(e["nom"]) not in
                  {normaliser_nom(c["nom"]) for c in collections}]
    if manquantes:
        print()
        print("  dans filtres.yaml mais absentes de l'export :")
        for nom in manquantes:
            print("    - %s" % nom)
    print()


def _executer(args):
    dossier, chemin_posts, chemin_collections = localiser_export(args.export)

    if args.init_config:
        collections, _ = charger_collections(chemin_collections)
        if not collections:
            raise ErreurFiltre(
                "aucune collection lisible dans %s\n"
                "  → vérifie que l'export contient bien "
                "saved_collections.json" % chemin_collections)
        chemin_config = Path(args.config)
        if chemin_config.exists() and not args.force:
            raise ErreurFiltre("%s existe déjà — relance avec --force pour "
                               "l'écraser" % chemin_config)
        ecrire_config_initiale(collections, chemin_config, args.export)
        print("✍️  %s écrit — %d collection(s), toutes « garder: true »."
              % (chemin_config.name, len(collections)))
        print("    Ouvre-le, passe à false ce qui ne t'intéresse pas, puis :")
        print("      python filtre.py --export \"%s\" --rapport" % args.export)
        return 0

    regles, avertissements = charger_config(args.config)
    for avertissement in avertissements:
        print("⚠️  %s" % avertissement)
    collections, index = charger_collections(chemin_collections)
    table = table_collections(regles)

    if args.liste_collections:
        _afficher_liste_collections(collections, index, regles, table,
                                    chemin_collections)
        return 0

    posts = charger_posts(chemin_posts)
    if not posts:
        raise ErreurFiltre("aucun post lisible dans %s — vérifie le fichier"
                           % chemin_posts)

    journal = charger_journal(args.journal)
    journal_affiche = "aucun"
    if journal:
        chemin_utilise = args.journal or str(Path(__file__).with_name(
            "journal.json"))
        journal_affiche = "%s (%d entrée(s))" % (chemin_utilise, len(journal))

    comptes = Counter()
    exemples = defaultdict(list)
    retenus, deja = [], 0
    for post in posts:
        verdict, motif = classer(post, regles, table, index)
        if verdict == "revoir":
            verdict = regles["defaut"]
            motif = "%s  (defaut : %s)" % (motif, regles["defaut"])
        comptes[(verdict, motif)] += 1
        if verdict != "garder":
            continue
        if len(exemples[motif]) < args.exemples:
            extrait = post["legende"][:90].replace("\n", " ").strip()
            exemples[motif].append(extrait or post["url"])
        if deja_ingere(journal, post["url"]):
            deja += 1
            continue
        retenus.append(post["url"])
    if args.limite > 0:
        retenus = retenus[:args.limite]

    print("export  : %s" % dossier)
    print("journal : %s" % journal_affiche)
    print()
    print("posts sauvegardés dans l'export : %d" % len(posts))
    print("déjà ingérés (journal)          : %d" % deja)
    print("à ingérer après filtre          : %d" % len(retenus))
    print("verdict par défaut (`defaut`)   : %s" % regles["defaut"])
    print()
    print("--- détail ---")
    for (verdict, motif), nombre in comptes.most_common():
        print("  %5d  %s · %s" % (nombre, verdict, motif))
        for exemple in exemples.get(motif, []):
            print("         ex. %s" % exemple)
    hors_config = [(c["nom"], len(c["medias"])) for c in collections
                   if normaliser_nom(c["nom"]) not in table]
    if hors_config:
        print()
        for nom, nombre in sorted(hors_config):
            print("⚠️  « %s » (%d post(s)) est dans l'export mais pas dans "
                  "filtres.yaml : ajoute-la, ou laisse-la dehors."
                  % (nom, nombre))

    if args.rapport:
        print()
        print("rapport seul : aucun fichier écrit ✓")
        return 0

    texte = "\n".join(retenus) + ("\n" if retenus else "")
    Path(args.sortie).write_text(texte, encoding="utf-8")
    print()
    if retenus:
        print("liste écrite : %s (%d lien(s))" % (args.sortie, len(retenus)))
        print("puis : python ingest.py %s" % args.sortie)
    else:
        print("aucun lien retenu — rien à ingérer (regarde le détail "
              "ci-dessus)")
    return 0


def main():
    parseur = argparse.ArgumentParser(
        prog="filtre.py",
        description="Choisit quoi ingérer dans un export Instagram, avant de "
                    "lancer la transcription. Tout est local.",
        epilog="exemples :\n"
               "  python filtre.py --export \"…/instagram-mon_compte\" "
               "--init-config\n"
               "  python filtre.py --export \"…/instagram-mon_compte\" "
               "--rapport\n"
               "  python filtre.py --export \"…/instagram-mon_compte\"\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parseur.add_argument("--export", required=True,
                         help="dossier (ou fichier) de l'export Instagram")
    parseur.add_argument("--config", default=str(CONFIG_DEFAUT),
                         help="fichier de règles (défaut : filtres.yaml du "
                              "dossier)")
    parseur.add_argument("--sortie", default=SORTIE_DEFAUT,
                         help="où écrire la liste retenue (défaut : %s)"
                              % SORTIE_DEFAUT)
    parseur.add_argument("--journal", default=None,
                         help="journal.json du vault, pour ne pas refaire "
                              "l'existant (défaut : celui du dossier, s'il "
                              "existe)")
    parseur.add_argument("--init-config", action="store_true",
                         help="écrit un filtres.yaml de départ depuis les "
                              "collections de l'export, puis sort")
    parseur.add_argument("--force", action="store_true",
                         help="autorise --init-config à écraser un filtres.yaml "
                              "existant")
    parseur.add_argument("--rapport", action="store_true",
                         help="affiche le rapport sans écrire de fichier")
    parseur.add_argument("--liste-collections", action="store_true",
                         help="affiche les collections de l'export et leur "
                              "verdict, puis sort")
    parseur.add_argument("--exemples", type=int, default=2,
                         help="exemples de légende affichés par motif "
                              "(0 = aucun)")
    parseur.add_argument("--limite", type=int, default=0,
                         help="ne retenir que les N premiers liens (pour un "
                              "essai)")
    args = parseur.parse_args()

    try:
        return _executer(args)
    except ErreurFiltre as erreur:
        print("✖ %s" % erreur)
        return 1
    except KeyboardInterrupt:
        print("\nInterrompu.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
