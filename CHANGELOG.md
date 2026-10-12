# Journal des versions

## Non publié

En préparation 🚧

- **Correctif Safari** : sur iPhone et Mac avec Safari, « Demander » affichait « Reconnecte Bobine » au lieu de répondre. La page imposait une politique de référent trop stricte qui faisait envoyer une origine vide, refusée par le contrôle de sécurité. Corrigé sans assouplir ce contrôle.

- **Demander (refonte, étape 3, première partie)** : questions directement dans la page servie, réponses avec liens vers les fiches, recherche locale et extraits plafonnés ; une question depuis une fiche reste limitée à cette vidéo. Le serveur de page est partagé avec Mac et reste local sur Mac. La copie iCloud garde sa lecture seule, sans bouton inopérant. Clé conservée côté serveur, protections intersites, quotas persistants, échéances strictes et conversations uniquement dans l'onglet. Le profil éditable viendra dans une PR distincte.

- **Finitions et captures** : encadrés mieux équilibrés (« Pour toi », Profil), texte de la recherche raccourci pour tenir sur iPhone, captures du README refaites à partir d'une bibliothèque fictive (liste, fiche, iPhone, carte), deux fois plus légères au total.

- **Mémo, « À retenir » et « Pour toi » (refonte, étape 2)** : avec une clé API, chaque fiche gagne un onglet Mémo (idée centrale, points clés, étapes, outils cités) et un encadré « À retenir ». Un profil facultatif (`Mon profil.txt`, proposé à l'installation) ajoute un bloc « Pour toi » : ce que la vidéo t'apporte. Les nouvelles vidéos reçoivent tout en une seule demande ; les anciennes sont rattrapées petit à petit (10 par passage) sans toucher à leurs titres ni à leurs résumés. Quand le profil change, seuls les blocs « Pour toi » sont refaits ; sans profil, aucun texte personnel n'est envoyé. Nouvelle page Profil, recherche étendue aux mémos, en-tête compact sur mobile. Sans clé, rien ne change.

- **Nouvelle bibliothèque (refonte, étape 1)** : design épuré (blanc, gris platine, noir, l'ambre pour guider le regard), une fiche complète par vidéo (En bref, transcription lisible et cherchable, description d'origine, vidéos liées), recherche jusque dans les transcriptions, carte des thèmes aux nouvelles couleurs avec un lien « Lire la fiche ». Toujours lisible sans JavaScript, aucune ressource externe ; la copie iPhone contient désormais les transcriptions.

- **Simplicité et seconde revue** : messages courts (vidéo enregistrée, résumé à venir) ; détails techniques sous « Dépannage avancé ». Toutes les nouvelles vidéos sont indexées avant les appels à l'IA, même sans modèle ou après coupure réseau. Les réponses JSON incomplètes restent en attente. La limite quotidienne compte chaque essai, y compris les réessais ; elle ne bloque jamais les résumés.

- **Page « Galerie »** : refonte de `vault.html` : trois modes clair, sombre, système (choix mémorisé), dates des fiches, tri des plus récentes d'abord, séparateurs de mois, glyphes de plateforme (YouTube, Instagram, TikTok), carte entière cliquable, surlignage de recherche avec raccourci « / », favicon. Toujours lisible sans JavaScript.
- **Carte v2** : `graph.html` devient une carte de navigation : clic sur un thème pour filtrer la liste, clic sur une vidéo pour l'aperçu (résumé, date, boutons), survol qui met au point, nombre de fiches par bulle, points colorés par date avec légende, thèmes fusionnés automatiquement. Les points se glissent, et l'aimant 🧲 (près du zoom) choisit entre retour en place et points posés librement. `vault.html?theme=…` pré-filtre la liste.
- **Sans clé API** : les nouvelles fiches sont indexées « résumé en attente » et visibles dans les pages ; dès l'ajout d'une clé, les résumés en attente se remplissent tout seuls, sans doublon.
- **Édition Linux — réveil instantané** : dès qu'un lien arrive dans la boîte de réception (Raccourci du téléphone, `curl`, dépôt à la main), la relève part immédiatement (unité systemd `bobine-watch.path`) ; le réveil de 15 minutes reste en filet de sécurité.
- **Corrections** : les dates des fiches sont retrouvées même quand les liens de la fiche et de l'index diffèrent par leurs paramètres de suivi ; les compteurs s'accordent correctement (« 1 fiche », « 2 fiches ») dans le terminal, les pages et les notifications.
- **Fiabilité des résumés** : si le service d'IA échoue (clé refusée, crédit épuisé, modèle retiré), la fiche reste visible sur la page, marquée « résumé en attente », et elle est retentée à chaque passage (et non plus seulement à l'arrivée d'une nouvelle vidéo). Le message exact du fournisseur arrive dans `logs/watch.log`, avec une notification si ça dure environ une heure. Le modèle se change en une ligne (`API_MODEL=…`), Gemini est documenté, et `LANGUE_RESUMES=en` donne des résumés en anglais. Les longues fiches envoient leur début et leur fin.
- **Sécurité** : une réponse du modèle ne peut plus fabriquer de fausse entrée ni de lien dans l'index ; seuls les liens `http(s)` deviennent cliquables ; un titre contenant un repère du modèle (`__SVG__`, `__CHIPS__`…) ne casse plus les pages ; `config.env` est lu sans être exécuté (une valeur non guillemetée avec une espace ne lance plus de commande) ; les chemins passés à AppleScript ne peuvent plus casser le script ; le jeton du serveur de liens est masqué dans les journaux, et les deux serveurs coupent les clients trop lents ; les sauvegardes `config.env.bak-*` (qui contiennent la clé) sont ignorées par git et lisibles par toi seul ; Crush n'a plus du tout accès aux outils d'écriture, de commande et d'internet.
- **Robustesse** : une même vidéo partagée deux fois (paramètres de suivi différents) n'est plus traitée ni résumée deux fois ; écritures atomiques (journal, index, pages) et reprise automatique d'un `journal.json` abîmé ; le plafond quotidien compte aussi les essais ratés ; nettoyage des fichiers temporaires après un échec ; nom de repli stable ; `graphe.py` retrouve les fiches YouTube ; les dates des vidéos YouTube ne se mélangent plus.
- **Installation et désinstallation** : une réinstallation garde les réglages avancés (chemins, cookies, notification, jeton, mot de passe de la page) ; un `README.md` ou `.gitignore` déjà présent n'est plus écrasé ; les dossiers déjà remplis sont refusés comme nouvelle destination ; la désinstallation arrête les services et conserve toujours les fichiers locaux, sans suppression automatique de la bibliothèque.
- **Tests et CI** : Tests supplémentaires pour les pages, les réponses piégées, les échecs du service, le journal, la lecture de `config.env`, l'installation et la conservation des fichiers. shellcheck et ruff sont vérifiés localement ; leur ajout à la CI demande encore une modification du workflow.
- **Documentation et projet** : README anglais par défaut (`README.fr.md` pour le français), guide Linux aussi en anglais, explications de confidentialité précisées (copie iCloud optionnelle, envois au fournisseur choisi), licence MIT standard reconnue par GitHub, modèles d'issues et de pull request, `SECURITY.md`, bouton « Star » dans l'en-tête des deux README.

## v1.2.0 (7 octobre 2026)

L'édition Linux 🐧

- **Édition Linux/VPS** : le portage serveur rejoint le dépôt, dossier `linux/` : installeur guidé, réveil systemd (au lieu de launchd), boîte de réception locale, serveur de liens (`POST /push`, envoie tes liens depuis un Raccourci iPhone), page servie à distance, modèles systemd et tunnel documentés. Le cœur (ingestion, transcription, résumés, pages) est partagé avec l'édition Mac ; la CI teste les deux et garde un garde-fou : le cœur ne peut pas dériver.
- **Accueil deux éditions** : bannière neutre (« Sur ton Mac. Sur ton serveur. »), badges de plateforme propres, README de vault dédié côté Mac.
- **Libellés** : les pages disent « mes vidéos sauvegardées » (Reels, TikTok et YouTube) ; captures du README rafraîchies.
- **Robustesse** : `enrichir` ignore les fichiers cachés (« ._ » AppleDouble semés par certains transferts macOS).

Publication : https://github.com/wrouhli/bobine/releases/tag/v1.2.0

## v1.1.0 (7 octobre 2026)

L'import de masse 🎛️

- **Filtre d'import** : `filtre.py`. Avant de lancer une longue transcription, choisis quoi ingérer depuis un export Instagram : tri exact par tes collections, mots-clés en filet de secours, `--init-config` et `--rapport` pour vérifier. Tout est local, rien de personnel n'est versionné.
- **Vérifications automatiques** : chaque PR lance les tests et les contrôles de syntaxe (GitHub Actions, Python 3.10 + 3.12) ; badge de statut dans le README.
- **Sécurité** : séparateur `--` avant chaque lien envoyé à yt-dlp/gallery-dl : un lien ne peut jamais être pris pour une option de l'outil ; import inutilisé retiré.
- **Tests** : première suite de tests unitaires (lançable sans rien installer) : sous-titres SRT/VTT, identifiants de liens, noms de fichiers.

Publication : https://github.com/wrouhli/bobine/releases/tag/v1.1.0

## v1.0.0 (3 octobre 2026)

Première version publique 🎞️

- **iPhone → Mac** : tu partages une Reel, un TikTok ou une vidéo YouTube, et elle devient une fiche locale (téléchargement audio, transcription, résumé facultatif).
- **Ingestion robuste** : sous-titres YouTube d'abord (quelques secondes), transcription locale (Whisper) sinon ; garde-fous 15 par passage / 50 par jour, 2 essais maximum.
- **Index et pages** : `index.md` (résumés + thèmes), `vault.html` (recherche, pastilles, lisible sans JavaScript), carte des thèmes `graph.html`.
- **Installation guidée** : choix du nom et de l'emplacement, environnement Python, dépendances, réveil automatique (launchd, un seul à la fois), copie iCloud pour l'iPhone.
- **Désinstallation propre** en double-clic (réveil, iCloud, dossier), sans jamais toucher aux autres vaults.
- **Gatekeeper** : `.command` en double-clic, avec la procédure d'autorisation documentée.
- **Bonus Crush** : interroge ton vault au Terminal avec la même clé API (lecture seule, télémétrie désactivée).
- Licence MIT ; **zéro donnée personnelle** dans le repo.

Publication : https://github.com/wrouhli/bobine/releases/tag/v1.0.0
