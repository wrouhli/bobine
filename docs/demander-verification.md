# Demander : revue et vérification avant fusion

Première PR de l'étape 3. Le profil reste en lecture seule. La fusion exige la revue de Hermes et les tests du propriétaire sur oneplus, Mac et iPhone. Les déploiements sur ces machines restent chez Hermes.

## Ce qui change

- `demander.py` : lecture bornée et confinée de la bibliothèque, recherche lexicale, cinq vidéos maximum, citations contrôlées. Depuis une fiche, une seule vidéo peut servir de source. Pas d'outils, de terminal ni de navigation web pour le modèle.
- `page_server.py` : partagé entre les deux éditions. La commande Mac `--local` refuse toute adresse autre que `127.0.0.1`. Le mode distant conserve Basic ou une protection amont explicitement configurée.
- `generate_page.py` : découverte du chat via une requête de même origine, seulement en HTTP(S). Aucun appel réseau du chat en `file://`, aucun jeton dans les fichiers HTML. Pas de stockage de conversation dans localStorage, sessionStorage ou sur disque.
- Installateurs : copie des nouveaux fichiers, régénération gratuite des pages existantes ; LaunchAgent Mac distinct du réveil, raccourci HTTP seulement après vérification de démarrage, secours fichier conservé. Les chemins avec espaces et caractères spéciaux, le VAULT personnalisé et les services d'autres installations sont testés.
- Désinstallateurs : services reconnus uniquement, jamais suppression de la bibliothèque. Le désinstallateur Linux reconnaît les chemins échappés produits par l'activation. Un même dossier est reconnu sous son chemin affiché comme sous son chemin réel (lien symbolique, ou /var vers /private/var sur macOS), sans jamais admettre un autre dossier.

## Modèle de protection

Le serveur vérifie l'authentification, l'origine exacte, Host et le jeton d'en-tête. Il exige du JSON pour les POST. `Sec-Fetch-Site`, lorsqu'il est présent, doit annoncer la même origine. Une requête privée sans Origin est refusée, même avec le jeton. Pas de CORS permissif ; `X-Forwarded-*` n'est pas utilisé pour inventer une origine de confiance.

L'origine protège contre les autres sites dans un navigateur ; elle n'authentifie pas un client direct. Le mot de passe ou le contrôle d'accès en amont reste nécessaire à distance. En cas de fuite du mot de passe, les limites s'appliquent à toute l'installation, indépendamment de l'adresse IP annoncée.

- 12 connexions traitées au maximum ; 10 secondes au total pour recevoir les en-têtes et le corps, même si le client envoie régulièrement quelques octets.
- Une réponse en cours par vault, avec verrou interprocessus. Lecture du corps avant prise du verrou moteur.
- 10 demandes admises/minute, 100 sur 24 heures glissantes. Quota horodaté en `.bobine-demandes.json`, permissions 600, écriture atomique, verrou interprocessus. Les tentatives admises comptent même sans résultat ou après panne. Un fichier abîmé bloque les nouvelles demandes au lieu de réinitialiser silencieusement le budget.
- Les tentatives rejetées pour authentification/origine ne consomment pas le budget d'admission légitime. Une limite séparée de 120 requêtes API valides/minute borne la découverte et les appels.
- Demande HTTP limitée à 32 Kio ; question à 2 000 caractères ; historique à 6 messages de 800 caractères ; contexte modèle à 16 000 caractères, sortie à 1 200 tokens et 6 000 caractères.
- Une seule tentative fournisseur par question ; aucune relance automatique, redirections interdites. Travail isolé dans un enfant sans shell : entrée sur stdin, configuration lue dans l'enfant, aucune clé ni question dans argv. Limite murale de 60 secondes, interruption et récolte de l'enfant, watchdog autonome. Cela ne garantit pas une annulation/facturation nulle chez le fournisseur.
- Les lectures de bibliothèque refusent symlinks, FIFO et fichiers spéciaux. Fichier 4 Mio maximum, index 8 Mio/10 000 entrées, ensemble lu 64 Mio. Les lectures historiques de `config.env` et des HTML ne constituent pas un bac à sable contre un acteur ayant déjà le contrôle du disque local.

## Vérifications automatiques

À lancer dans le dépôt, dans un environnement Python 3.10 puis 3.12 :

```bash
python3 -m unittest discover -s tests
python3 -m unittest discover -s linux/tests
ruff check --select F,B --target-version py310 *.py linux/*.py tests/*.py linux/tests/*.py
shellcheck -S warning install.sh desinstaller.sh watch.sh "👉 2. Installer Bobine.command" \
  linux/install-linux.sh linux/desinstaller-linux.sh linux/watch-linux.sh linux/activer-page-web.sh
```

Les tests de page exécutent également un harnais JavaScript quand Node est disponible, sans réseau. Les tests HTTP utilisent des sockets loopback et des fournisseurs simulés, jamais une clé réelle. Le test de parité du serveur inclut les nouveaux modules et tests, sans modification du workflow GitHub.

## Migration contrôlée par Hermes

Toujours sauvegarder les scripts remplacés, les services, le raccourci et la configuration avant modification. Ne jamais remplacer `config.env` par l'exemple du dépôt. Ne pas relancer automatiquement une activation de tunnel déjà en place : son adresse et sa route doivent rester identiques.

### Oneplus, en premier

1. Déployer les modules partagés `demander.py`, `page_server.py`, `generate_page.py` de l'édition Linux, avec le reste de cette PR selon le mode de mise à jour habituel. Garder ingest/enrichir/graphe et les dépendances présents.
2. Ajouter uniquement `PAGE_ORIGIN=https://adresse-actuelle-de-bobine` à la configuration personnelle. L'origine est sans chemin ni slash final ; ne pas deviner le domaine.
3. Régénérer gratuitement la page avec `generate_page.py --vault <dossier effectif>` puis redémarrer le service de page existant. Aucun besoin de relancer l'ingestion ou les mémos.
4. Vérifier Basic/protection amont, Host préservé par le tunnel, chat visible et réponses sourcées. Sans PAGE_ORIGIN, l'ancienne adresse reste lisible mais le chat distant n'est pas activé.

### Mac, ensuite

1. Déployer les mêmes modules. Installer le LaunchAgent de page avec l'installateur mis à jour, d'abord en bac à sable. Il utilise le Python du venv, le dossier du code et le VAULT effectif sans exécuter la configuration comme du shell.
2. Vérifier que seule l'interface `127.0.0.1:8786` écoute. Le raccourci Ma page doit viser cette adresse seulement si le service fonctionne.
3. Port déjà occupé, service personnalisé ou service d'un autre vault : il est conservé, le mode fichier reste le secours. Ne jamais tuer un processus inconnu pour libérer le port.
4. Vérifier que la relève et le serveur de liens existants restent inchangés.

## Scénarios manuels obligatoires

- Bibliothèque fictive : question pertinente, réponse sans résultat (zéro appel fournisseur), question depuis une fiche, suivi, nouvelle conversation, source cliquable, accents et mobile 320/390 px.
- Ajout d'une vidéo pendant que l'onglet reste ouvert : sa citation doit ouvrir une page actualisée, jamais disparaître silencieusement.
- Clé absente, refusée, crédit épuisé, fournisseur arrêté, réponse JSON invalide et sans sources valides : message compréhensible, brouillon préservé, pas de relance automatique.
- Une requête d'un autre site, même avec un jeton connu, est refusée avant le fournisseur. Formulaire HTML, Origin nulle/absente, mauvais Host, faux X-Forwarded-Host et pré-vol refusés. Refaire depuis le chemin public oneplus.
- Vérifier les limites publiques sans dépenses en simulant le fournisseur : fréquence, quota journalier persistant, simultanéité, corps trop gros et client lent. Aucun dialogue ni secret dans les logs.
- Serveur redémarré : ancien jeton refusé, reconnexion manuelle sans réenvoyer la question automatiquement. Serveur arrêté : bibliothèque statique encore lisible.
- iPhone via adresse serveur : chat opérationnel derrière la protection habituelle. iPhone via fichier iCloud : lecture seule sans tentative de connexion ni contrôle de chat actif.
- JavaScript désactivé : bibliothèque, fiche et profil lisibles, pas de chat proposé.
- Profil, `raw/`, `index.md`, `journal.json` et mémos inchangés après des questions. Seul le compteur horodaté et ses verrous peuvent apparaître.

## Limites assumées

Recherche lexicale, pas recherche sémantique exhaustive. Les liens cités sont vérifiés contre les fiches envoyées ; le sens de chaque phrase du modèle n'est pas certifié. Le chat répond en français. Les historiques sont limités à l'onglet et les profils Mac/serveur ne sont pas synchronisés automatiquement. Le formulaire de profil n'appartient pas à cette PR.
