#!/usr/bin/env python3
"""
ingest.py — transforme une liste de liens TikTok / Instagram / YouTube en fiches Markdown.

Pour chaque vidéo :
  1. récupère les métadonnées (titre, description, auteur, hashtags)
  2. YouTube : récupère les sous-titres quand ils existent (sans télécharger)
  3. sinon, télécharge l'audio et le transcrit en local avec faster-whisper
  4. écrit une fiche Markdown dans vault/raw/

Le script reprend là où il s'est arrêté : on peut le couper (Ctrl+C) et le
relancer sans retraiter ce qui est déjà fait.

Usage :
    python ingest.py mes_liens.txt
    python ingest.py saved_posts.json --cookies chrome
    python ingest.py liens.txt --limite 20        (pour tester sur 20 vidéos)
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- configuration

VAULT = Path.home() / "vault"          # modifiable avec --vault
MODELE_WHISPER = "small"               # tiny / base / small / medium
PAUSE_ENTRE_VIDEOS = 3                 # secondes, pour ne pas se faire bloquer

YTDLP = [sys.executable, "-m", "yt_dlp"]
GALLERYDL = [sys.executable, "-m", "gallery_dl"]

MOTIF_LIEN = re.compile(
    r"https?://(?:www\.|vm\.|vt\.|m\.)?(?:tiktok\.com|instagram\.com|youtube\.com|youtu\.be)/[^\s\"'<>,\)\]]+"
)


# ---------------------------------------------------------------- utilitaires

def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def pluriel(n, mot):
    """Accord simple : singulier pour 0 et 1 (« 0 échec », « 1 fiche »),
    pluriel à partir de 2 (« 2 fiches »)."""
    return f"{n} {mot}" if n < 2 else f"{n} {mot}s"


def verifier_outils():
    """Verifie que yt-dlp et ffmpeg repondent avant de commencer."""
    manquants = []

    try:
        subprocess.run(YTDLP + ["--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        manquants.append("yt-dlp  ->  pip install yt-dlp")

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        if sys.platform == "darwin":
            manquants.append("ffmpeg  ->  brew install ffmpeg")
        else:
            manquants.append("ffmpeg  ->  sudo apt install ffmpeg  (Debian/Ubuntu)")

    if manquants:
        log("ERREUR : outil(s) manquant(s)")
        for m in manquants:
            log(f"   {m}")
        sys.exit(1)


def extraire_liens(chemin):
    """Récupère toutes les URLs TikTok/Instagram/YouTube d'un fichier, quel que soit
    son format (txt, csv, json d'export). Les doublons sont supprimés."""
    texte = Path(chemin).read_text(encoding="utf-8", errors="ignore")
    liens, vus = [], set()
    for lien in MOTIF_LIEN.findall(texte):
        lien = lien.rstrip(".,;")
        if lien not in vus:
            vus.add(lien)
            liens.append(lien)
    return liens


def options_cookies(cookies, lien=""):
    """--cookies accepte soit un nom de navigateur (firefox, edge...),
    soit le chemin d'un fichier cookies.txt exporte depuis le navigateur.
    Les liens YouTube sont traités SANS cookies (voir commentaire plus bas)."""
    if not cookies:
        return []
    # YouTube : les cookies d'un navigateur mal connecté (ou pas connecté du
    # tout) à YouTube font échouer l'extraction (« No video formats found »).
    # Sans cookies, ça marche : on ne les envoie donc pas pour YouTube.
    if "youtube.com" in lien or "youtu.be" in lien:
        return []
    if Path(cookies).exists():
        return ["--cookies", str(Path(cookies).resolve())]
    return ["--cookies-from-browser", cookies]


def charger_journal(chemin):
    if chemin.exists():
        return json.loads(chemin.read_text(encoding="utf-8"))
    return {}


def sauver_journal(chemin, journal):
    chemin.write_text(
        json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def nom_plateforme(lien):
    """« YouTube », « TikTok » ou « Instagram » selon le lien."""
    if "youtube.com" in lien or "youtu.be" in lien:
        return "YouTube"
    if "tiktok" in lien:
        return "TikTok"
    return "Instagram"


def identifiant(lien):
    """Un nom de fichier court et sûr, dérivé de l'URL."""
    # YouTube : l'identifiant est dans la query (watch?v=...) ou le chemin
    # (youtu.be/..., /shorts/...). Le dernier segment d'un lien « watch?v= »
    # serait « watch », inutilisable comme nom de fiche.
    if "youtube.com" in lien or "youtu.be" in lien:
        trouve = re.search(
            r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{6,})", lien
        )
        if trouve:
            return f"yt_{trouve.group(1)}"
    # Couper la query AVANT de prendre le dernier segment : un lien partagé
    # par l'appli instagram (".../reel/ABC/?stkn=...") a un "/" juste avant
    # le "?", donc l'ancien ordre donnait un nom vide (repli sur un hash).
    fin = lien.split("?")[0].rstrip("/").split("/")[-1]
    fin = re.sub(r"[^A-Za-z0-9_-]", "", fin)[:40]
    plateforme = "tiktok" if "tiktok" in lien else "insta"
    return f"{plateforme}_{fin or str(abs(hash(lien)))[:10]}"


# ---------------------------------------------------------------- étapes

def recuperer_metadonnees(lien, cookies):
    commande = YTDLP + ["--dump-json", "--no-warnings", "--skip-download",
                        "--no-playlist"]
    commande += options_cookies(cookies, lien)
    # « -- » : tout ce qui suit est positionnel — un lien ne peut jamais être
    # pris pour une option de l'outil, même s'il commence par « - ».
    commande += ["--", lien]
    resultat = subprocess.run(commande, capture_output=True, text=True, timeout=120)
    if resultat.returncode != 0:
        raise RuntimeError((resultat.stderr or "yt-dlp a échoué").strip()[:300])
    return json.loads(resultat.stdout.splitlines()[0])


def telecharger_media(lien, dossier, nom, cookies):
    """Télécharge l'audio (m4a) de la vidéo — et rien d'autre (plus d'images)."""
    audio = dossier / f"{nom}.m4a"

    base = YTDLP + ["--no-warnings", "--quiet", "--no-playlist"] + options_cookies(cookies, lien)

    subprocess.run(
        base + ["-f", "bestaudio", "-x", "--audio-format", "m4a",
                "-o", str(dossier / f"{nom}.%(ext)s"), "--", lien],
        capture_output=True, timeout=300,
    )
    return audio if audio.exists() else None


def nettoyer_srt(texte):
    """SRT → texte brut : retire numéros et minuteurs, puis fusionne les cues
    qui se chevauchent (les sous-titres automatiques « roulent » : chaque cue
    répète la fin du précédent avant d'ajouter la suite)."""
    cues = []
    for bloc in re.split(r"\n\s*\n", texte):
        morceaux = []
        for ligne in bloc.splitlines():
            ligne = ligne.strip()
            if not ligne or "-->" in ligne or ligne.isdigit():
                continue
            if ligne.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
                continue
            morceaux.append(re.sub(r"<[^>]+>", "", ligne))
        if morceaux:
            cues.append(" ".join(morceaux))

    mots = []
    for cue in cues:
        nouveau = cue.split()
        if not nouveau:
            continue
        # plus grand recouvrement « fin du texte == début du cue »
        recouvrement = 0
        for k in range(min(len(mots), len(nouveau), 30), 0, -1):
            if mots[-k:] == nouveau[:k]:
                recouvrement = k
                break
        if recouvrement >= 2:
            mots.extend(nouveau[recouvrement:])
        else:
            mots.extend(nouveau)
    return " ".join(mots).strip()


def recuperer_sous_titres(lien, meta, dossier, nom, cookies):
    """Récupère le texte des sous-titres YouTube SANS télécharger la vidéo.

    Priorité : langue d'origine (métadonnée « language » quand elle existe),
    puis français, puis anglais. Retourne "" si aucun sous-titre n'est
    disponible — on retombe alors sur Whisper.
    """
    langue_meta = (meta.get("language") or "").split("-")[0].strip().lower()
    if langue_meta == "en":
        langues = ["en"]                 # vidéo anglaise : une seule requête
    elif langue_meta:
        langues = [langue_meta, "en"]    # langue d'origine, puis l'anglais
    else:
        langues = ["fr", "en"]           # langue inconnue : français, puis anglais
    # Codes EXACTS et au plus 2 langues : chaque langue en plus est une requête
    # de plus, et YouTube rate-limite vite (erreur 429).
    motif = ",".join(langues)

    base = dossier / f"subs_{nom}"
    commande = YTDLP + ["--no-warnings", "--quiet", "--skip-download",
                        "--no-playlist", "--write-auto-subs", "--write-subs",
                        "--sub-langs", motif, "--convert-subs", "srt",
                        "-o", str(base)]
    commande += options_cookies(cookies, lien)
    commande += ["--", lien]

    def fichiers_sous_titres():
        # .srt d'abord (convertis), puis .vtt : quand une autre langue fait un
        # 429, yt-dlp saute l'étape de conversion — mais le .vtt EST là et
        # c'est du texte parfaitement exploitable.
        return (sorted(dossier.glob(f"subs_{nom}.*.srt"))
                + sorted(dossier.glob(f"subs_{nom}.*.vtt")))

    fichiers = []
    for tentative in (1, 2):
        resultat = subprocess.run(commande, capture_output=True, text=True,
                                  timeout=300)
        fichiers = fichiers_sous_titres()
        if fichiers:
            break
        if tentative == 1 and "429" in (resultat.stderr or ""):
            time.sleep(25)  # rate-limit YouTube : on retente une fois

    if not fichiers:
        return ""

    def priorite(fichier):
        nom_fichier = fichier.name
        for rang, langue in enumerate(langues):
            marqueur = "." + langue
            position = nom_fichier.find(marqueur)
            if position != -1:
                suivant = nom_fichier[position + len(marqueur):position + len(marqueur) + 1]
                if suivant in (".", "-", ""):
                    return rang
        return len(langues)

    choisi = sorted(fichiers, key=priorite)[0]
    texte = nettoyer_srt(choisi.read_text(encoding="utf-8", errors="ignore"))

    for fichier in fichiers:  # on ne garde pas les fichiers de sous-titres
        try:
            fichier.unlink()
        except OSError:
            pass
    return texte


def duree_video(fichier):
    """Durée en secondes du fichier téléchargé, lue via `ffmpeg -i`
    (quand yt-dlp ne fournit pas la durée et sans ffprobe disponible)."""
    if fichier is None:
        return 0
    try:
        resultat = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(fichier)],
            capture_output=True, text=True, timeout=30,
        )
        trouve = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
                           resultat.stderr or "")
        if not trouve:
            return 0
        return (int(trouve.group(1)) * 3600 + int(trouve.group(2)) * 60
                + float(trouve.group(3)))
    except (OSError, ValueError):
        return 0


def transcrire(audio, modele):
    if audio is None:
        return ""
    segments, _ = modele.transcribe(str(audio), vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


def recuperer_carrousel(lien, cookies):
    """Post Instagram sans vidéo (carrousel photo) : on ne récupère QUE la
    légende — plus aucune image n'est téléchargée (pas de fonctionnalité
    images dans ce projet)."""
    commande = GALLERYDL + ["-j"]
    commande += options_cookies(cookies, lien)
    commande += ["--", lien]
    resultat = subprocess.run(commande, capture_output=True, text=True, timeout=300)

    def chercher_legende(objet):
        if isinstance(objet, dict):
            for cle in ("description", "caption"):
                valeur = objet.get(cle)
                if isinstance(valeur, str) and valeur.strip():
                    return valeur.strip()
            for valeur in objet.values():
                trouve = chercher_legende(valeur)
                if trouve:
                    return trouve
        elif isinstance(objet, list):
            for element in objet:
                trouve = chercher_legende(element)
                if trouve:
                    return trouve
        return ""

    sortie = (resultat.stdout or "").strip()
    if not sortie:
        return ""
    try:
        return chercher_legende(json.loads(sortie))
    except json.JSONDecodeError:
        pass
    for ligne in sortie.splitlines():
        try:
            trouve = chercher_legende(json.loads(ligne))
        except json.JSONDecodeError:
            continue
        if trouve:
            return trouve
    return ""


def ecrire_fiche(dossier, nom, lien, meta, transcription, genre, source_texte):
    contenu = f"""---
source: {lien}
plateforme: {nom_plateforme(lien)}
genre: {genre}
auteur: {meta.get("uploader") or meta.get("channel") or "inconnu"}
duree_s: {meta.get("duration") or ""}
texte: {source_texte}
traite_le: {datetime.now():%Y-%m-%d}
statut: brut
---

# {(meta.get("title") or nom)[:120]}

## Description
{(meta.get("description") or "").strip() or "(vide)"}

## Transcription
{transcription or "(pas de texte récupéré)"}
"""
    (dossier / f"{nom}.md").write_text(contenu, encoding="utf-8")


# ---------------------------------------------------------------- programme

def main():
    parseur = argparse.ArgumentParser()
    parseur.add_argument("fichier", help="fichier contenant les liens")
    parseur.add_argument("--vault", default=str(VAULT))
    parseur.add_argument("--cookies", default=None,
                         help="navigateur pour les cookies (chrome, firefox, edge)")
    parseur.add_argument("--limite", type=int, default=0,
                         help="ne traiter que les N premières vidéos")
    parseur.add_argument("--modele", default=MODELE_WHISPER)
    args = parseur.parse_args()

    verifier_outils()

    vault = Path(args.vault)
    dossier_raw = vault / "raw"
    dossier_temp = vault / ".temp"
    for d in (dossier_raw, dossier_temp):
        d.mkdir(parents=True, exist_ok=True)

    chemin_journal = vault / "journal.json"
    journal = charger_journal(chemin_journal)

    liens = extraire_liens(args.fichier)
    # On ne retente un échec que 2 fois : au-delà, c'est presque toujours un
    # post supprimé/privé, et insister fatigue Instagram plus qu'autre chose.
    a_faire = [
        l for l in liens
        if journal.get(l, {}).get("statut") != "ok"
        and journal.get(l, {}).get("tentatives", 0) < 2
    ]
    if args.limite:
        a_faire = a_faire[: args.limite]

    log(f"{pluriel(len(liens), 'lien')} trouvé{'' if len(liens) < 2 else 's'}, "
        f"{len(a_faire)} à traiter.")
    if not a_faire:
        return

    modele = None

    def obtenir_modele():
        """Charge Whisper seulement au besoin (les sous-titres l'évitent)."""
        nonlocal modele
        if modele is None:
            log(f"Chargement du modèle Whisper « {args.modele} » (long la 1re fois)...")
            from faster_whisper import WhisperModel
            modele = WhisperModel(args.modele, device="cpu", compute_type="int8")
        return modele

    reussites = echecs = 0
    for numero, lien in enumerate(a_faire, 1):
        nom = identifiant(lien)
        log(f"[{numero}/{len(a_faire)}] {lien}")
        try:
            erreur_meta = ""
            try:
                meta = recuperer_metadonnees(lien, args.cookies)
            except Exception as e:
                meta = {}  # carrousel, ou probleme d'acces
                erreur_meta = str(e).replace("\n", " ")[:300]

            audio = None
            transcription = ""
            source_texte = ""
            formats = meta.get("formats") or []
            est_video = bool(meta.get("duration")) or any(
                (f.get("vcodec") or "none") != "none" for f in formats
            )
            if est_video:
                genre = "video"
                # YouTube : les sous-titres d'abord (quelques secondes, sans
                # rien télécharger) ; sinon on retombe sur Whisper.
                if "youtube.com" in lien or "youtu.be" in lien:
                    sous_titres = recuperer_sous_titres(lien, meta,
                                                        dossier_temp, nom,
                                                        args.cookies)
                    if sous_titres:
                        transcription = sous_titres
                        source_texte = "sous-titres YouTube"
                if not transcription:
                    audio = telecharger_media(lien, dossier_temp, nom,
                                              args.cookies)
                    if audio is None:
                        # Rien récupéré du tout : souvent un rate-limit
                        # temporaire — on marque l'échec pour réessayer au
                        # prochain passage (mieux qu'une fiche vide "ok").
                        raise RuntimeError(
                            "aucun média récupéré (souvent un rate-limit — "
                            "réessai automatique au prochain passage)"
                        )
                    if not meta.get("duration"):
                        meta["duration"] = duree_video(audio)
                    transcription = transcrire(audio, obtenir_modele())
                    source_texte = "whisper (local)"
            else:
                genre = "carrousel"
                legende = recuperer_carrousel(lien, args.cookies)
                source_texte = "légende"
                if legende and not meta.get("description"):
                    meta["description"] = legende
                if not legende and not meta.get("description"):
                    raise RuntimeError(
                        "carrousel : aucune légende récupérée | yt-dlp : "
                        + (erreur_meta or "aucun message")
                    )

            ecrire_fiche(dossier_raw, nom, lien, meta, transcription,
                         genre, source_texte)

            if audio and audio.exists():
                audio.unlink()

            journal[lien] = {"statut": "ok", "fiche": f"{nom}.md"}
            reussites += 1
        except Exception as erreur:  # noqa: BLE001 — on continue quoi qu'il arrive
            log(f"    échec : {erreur}")
            tentatives = journal.get(lien, {}).get("tentatives", 0) + 1
            journal[lien] = {
                "statut": "echec",
                "erreur": str(erreur)[:300],
                "tentatives": tentatives,
            }
            echecs += 1

        sauver_journal(chemin_journal, journal)
        time.sleep(PAUSE_ENTRE_VIDEOS)

    log(f"Terminé — {pluriel(reussites, 'réussite')}, {pluriel(echecs, 'échec')}.")
    log(f"Fiches disponibles dans : {dossier_raw}")
    if echecs:
        log("Relance le script pour retenter uniquement les échecs.")


if __name__ == "__main__":
    main()
