# Journal des versions

## v1.1.0 — 7 octobre 2026

L'import de masse 🎛️

- **Filtre d'import** : `filtre.py` — avant de lancer une longue transcription, choisis quoi ingérer depuis un export Instagram : tri exact par tes collections, mots-clés en filet de secours, `--init-config` et `--rapport` pour vérifier. Tout est local, rien de personnel n'est versionné.
- **Vérifications automatiques** : chaque PR lance les tests et les contrôles de syntaxe (GitHub Actions, Python 3.10 + 3.12) — badge de statut dans le README.
- **Sécurité** : séparateur `--` avant chaque lien envoyé à yt-dlp/gallery-dl — un lien ne peut jamais être pris pour une option de l'outil ; import inutilisé retiré.
- **Tests** : première suite de tests unitaires (lançable sans rien installer) — sous-titres SRT/VTT, identifiants de liens, noms de fichiers.

Publication : https://github.com/wrouhli/bobine/releases/tag/v1.1.0

## v1.0.0 — 3 octobre 2026

Première version publique 🎞️

- **iPhone → Mac** : tu partages une Reel, un TikTok ou une vidéo YouTube, et elle devient une fiche locale (téléchargement audio, transcription, résumé facultatif).
- **Ingestion robuste** : sous-titres YouTube d'abord (quelques secondes), transcription locale (Whisper) sinon ; garde-fous 15 par passage / 50 par jour, 2 essais maximum.
- **Index et pages** : `index.md` (résumés + thèmes), `vault.html` (recherche, pastilles, lisible sans JavaScript), carte des thèmes `graph.html`.
- **Installation guidée** : choix du nom et de l'emplacement, environnement Python, dépendances, réveil automatique (launchd, un seul à la fois), copie iCloud pour l'iPhone.
- **Désinstallation propre** en double-clic (réveil, iCloud, dossier) — sans jamais toucher aux autres vaults.
- **Gatekeeper** : `.command` en double-clic, avec la procédure d'autorisation documentée.
- **Bonus Crush** : interroge ton vault au Terminal avec la même clé API (lecture seule, télémétrie désactivée).
- Licence MIT ; **zéro donnée personnelle** dans le repo.

Publication : https://github.com/wrouhli/bobine/releases/tag/v1.0.0
