<div align="center">
  <sub>🌍 <b>Français</b> · <a href="README.md">English</a></sub>
  <img src="assets/banniere.png" alt="Bobine : tes Reels sauvegardés deviennent une base locale, chez toi" width="820">
  <h1>🎞️ Bobine</h1>
  <p><b>Tes Reels, et n'importe quelle vidéo TikTok/YouTube, sauvegardés deviennent une base de connaissances locale, cherchable et interrogeable. Sur ton Mac ou ton serveur, chez toi.</b></p>
  <p>
    <a href="https://github.com/wrouhli/bobine/releases"><img src="https://img.shields.io/github/v/release/wrouhli/bobine?color=6C4DFF&label=version&style=flat" alt="Version"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/licence-MIT-blue.svg" alt="Licence : MIT"></a>
    <img src="https://img.shields.io/badge/macOS%20%2B%20iPhone-black?logo=apple" alt="macOS + iPhone">
    <a href="linux/README.md"><img src="https://img.shields.io/badge/Linux%20%2F%20VPS-black?logo=linux" alt="Linux / VPS"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
    <a href="https://github.com/wrouhli/bobine/actions/workflows/tests.yml"><img src="https://github.com/wrouhli/bobine/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  </p>
  <p>
    <a href="https://github.com/wrouhli/bobine/stargazers"><img src="https://img.shields.io/github/stars/wrouhli/bobine?style=for-the-badge&label=%E2%AD%90%20Mets%20une%20%C3%A9toile&color=6C4DFF&logo=github&logoColor=white" alt="⭐ Mets une étoile"></a>
  </p>
</div>

Tu partages une vidéo depuis ton iPhone. Quelques minutes plus tard, Bobine l'a téléchargée, transcrite, résumée et rangée dans une fiche. Le soir, tu ouvres une petite page web sur ton téléphone : tout est là, avec une recherche. **Et tout reste chez toi.**

> **Deux éditions, le même vault :**
> 🍎 **Mac + iPhone** : tu es au bon endroit. Télécharge le dossier, double-clique, c'est fini (iCloud, notifications, Crush).
> 🐧 **Linux / VPS**, la version serveur : installeur, réveil systemd, page en HTTPS → **[linux/](linux/README.md)**

> **🌍 Langue des résumés :** les résumés sont écrits en français par défaut. Une option permet de les avoir en anglais ; elle est expliquée dans les réglages avancés ci-dessous.

> **📥 Tu viens de télécharger le dossier ?** Ouvre d'abord **« 👉 1. LIS-MOI D'ABORD (installation) »** : cette page t'accompagne clic par clic pendant l'installation (questions de sécurité de macOS comprises). Tout est aussi détaillé dans la section [Installation](#installation).

---

## Sommaire

- [Aperçu](#aperçu)
- [Comment ça marche](#comment-ça-marche)
- [Ce qu'il te faut](#ce-quil-te-faut)
- [Installation](#installation)
- [Ton Bobine au quotidien](#ton-bobine-au-quotidien)
- [Importer un export Instagram](#importer-un-export-instagram)
- [Les coûts](#les-coûts)
- [Dépannage : les classiques](#dépannage--les-classiques)
- [Désinstaller Bobine](#désinstaller-bobine)
- [La structure du projet](#la-structure-du-projet)
- [FAQ](#faq)
- [Contribuer](#contribuer)
- [Auteur](#auteur)
- [Licence](#licence)
- [Édition Linux / VPS](linux/README.md)

## Aperçu

**Ta bibliothèque.** Recherche instantanée (jusque dans les transcriptions), filtres par thème, une carte par vidéo :

![Ta bibliothèque Bobine : recherche, thèmes, une carte par vidéo](assets/capture-liste.png)

**Une page par vidéo.** Le résumé, les points à retenir et un bloc « Pour toi » d'après ton profil *(avec une clé API)*, plus le mémo complet et la transcription :

![Une fiche : résumé, à retenir, pour toi](assets/capture-fiche.png)

**Sur ton iPhone aussi.** La même page dans ta poche, via iCloud sur Mac ou l'adresse de ton serveur sous Linux :

![Bobine sur iPhone : la bibliothèque et une fiche](assets/capture-iphone.png)

**La carte des thèmes.** Les sujets de ta collection, reliés entre eux :

![La carte des thèmes de ton Bobine](assets/capture-carte.png)

**Et tu peux lui poser des questions** depuis **Demander**, avec des liens vers les fiches utilisées. Crush reste disponible en alternative dans le Terminal.

*(Toutes ces captures proviennent d'un Bobine de démonstration.)*

## Comment ça marche

```
iPhone                        Mac                                    iPhone
──────                        ───                                    ──────
Partager ───────►  boîte iCloud ──►  toutes les 15 min :          ┌► Fichiers → iCloud Drive
  (Instagram,     (inbox.txt)        1. relève la boîte           │    → Bobine
   TikTok,                           2. télécharge l'audio         │    → vault.html
   YouTube…)                         3. transcription locale       │      (recherche + résumés)
                                     4. résumé (ta clé API)        │
                                     5. fiches + page ─────────────┘
```

- **Transcription locale** (Whisper) : gratuite. Pour YouTube, Bobine récupère d'abord les **sous-titres** (récupération de quelques kilo-octets, en secondes) et ne transcrit que s'il n'y en a pas.
- **Résumés** : *facultatifs*, avec ta propre clé API (DeepSeek, OpenAI, OpenRouter…), Bobine écrit pour chaque fiche un titre, des thèmes et un résumé concret, met à jour l'index et régénère les pages.
- **Garde-fous** : jamais de rafale de téléchargements (15 par passage, 50 essais par jour au maximum, échecs compris), jamais deux passages en même temps, un échec n'est retenté que 2 fois. Une fiche dont le résumé a échoué reste visible sur ta page, marquée « résumé en attente », et elle est retentée à chaque passage.

## Ce qu'il te faut

- un **Mac** + une connexion internet ;
- **Python 3.10 ou plus** (le script d'installation te guide) ;
- **ffmpeg** (`brew install ffmpeg`) ;
- *(facultatif, recommandé)* un **iPhone** pour le partage en un geste ;
- *(facultatif, recommandé)* une **clé API** pour les résumés : [DeepSeek](https://platform.deepseek.com) est le moins cher (quelques centimes pour des centaines de vidéos).

## Installation

L'installation est **interactive**, guidée du début à la fin : tu choisis le **nom** de ton vault et **où** l'installer, tu mets ta clé API si tu veux (facultatif), et Bobine fait le reste (environnement, dépendances, réveil automatique).

1. **Télécharge** ce dossier (« Code » → « Download ZIP »), puis décompresse-le (double-clic sur le fichier `.zip`).
2. Ouvre le dossier téléchargé et **commence par « 👉 1. LIS-MOI D'ABORD (installation) »** : cette page t'explique, clic par clic, les 2-3 questions de sécurité de macOS (c'est normal qu'il en pose, et c'est même sain).
3. **Double-clique sur « 👉 2. Installer Bobine.command »** et réponds aux questions (nom, emplacement, clé API facultative).
4. Si on te le demande : `brew install ffmpeg`.

> **🛡️ Les dialogues de macOS, en résumé** (tout est illustré, en images, dans la page ci-dessus) : clique **« Terminé »** (jamais « Placer dans la corbeille »), puis Réglages Système → **Confidentialité et sécurité** → « Ouvrir quand même », puis re-double-clique sur l'installateur.
>
> **Tu as cliqué « Placer dans la corbeille » ?** Pas de drame : clic droit sur le fichier dans la corbeille → « Remettre en place », ou re-décompresse le ZIP.

**Si tu préfères le Terminal**, tu peux lancer toi-même l'installateur. Lis le script avant de l'autoriser ; les demandes de sécurité dépendent des réglages de ton Mac. Place-toi dans le dossier téléchargé (astuce : tape `cd` suivi d'une espace, puis glisse le dossier dans la fenêtre du Terminal, et appuie sur Entrée), puis lance :

```bash
./install.sh    # bannière, questions guidées, environnement + dépendances...
```

À la fin, tout vit dans **le dossier de ton vault** (celui que tu as choisi) : si tu as choisi un dossier séparé, le dossier téléchargé ne sert plus à rien. Si tu as gardé Bobine dans le dossier téléchargé, conserve ce dossier.

*(Vérification facultative, dans le dossier de ton vault : `.venv/bin/python enrichir.py --dry-run`.)*

### *Facultatif* : la clé API des résumés

Ouvre `config.env` (créé par l'installation) et colle ta clé sur la bonne ligne :

```
DEEPSEEK_API_KEY=sk-…
```

C'est tout. Les autres lignes restent vides.

Si un résumé tarde, ta vidéo est quand même enregistrée. Bobine réessaie automatiquement : pas besoin de surveiller ou de relancer quoi que ce soit.

<details>
<summary>Autres fournisseurs et réglages avancés (facultatif)</summary>

D'autres fournisseurs marchent aussi, chacun avec sa ligne :

| Fournisseur | Ligne dans `config.env` | Modèle |
|---|---|---|
| DeepSeek | `DEEPSEEK_API_KEY=…` | `deepseek-chat` par défaut ; à changer avec `API_MODEL=…` |
| OpenAI | `OPENAI_API_KEY=…` | `API_MODEL=…` obligatoire (ex. `gpt-4o-mini`) |
| OpenRouter | `OPENROUTER_API_KEY=…` | `API_MODEL=…` obligatoire |
| Google Gemini | `GEMINI_API_KEY=…` | `API_MODEL=…` obligatoire |
| Tout service compatible OpenAI | `API_KEY=…` + `API_BASE_URL=…` | `API_MODEL=…` obligatoire |

Pour des résumés en anglais, ajoute `LANGUE_RESUMES=en` dans `config.env`. Les pages et les messages restent en français. Le modèle DeepSeek existant reste le défaut ; si le fournisseur ne l'accepte plus, tu peux en choisir un autre avec `API_MODEL=…`.

</details>

### *Facultatif* : ton profil (le bloc « Pour toi »)

Avec une clé API, chaque fiche gagne un onglet **Mémo** (l'idée centrale, les points clés, les étapes, les outils cités) et un encadré **À retenir**. Si tu te décris aussi en quelques lignes, chaque fiche ajoute un bloc **Pour toi** : ce que cette vidéo t'apporte, à toi.

L'installation pose la question une fois (Entrée pour passer). Tu peux l'écrire ou le changer à tout moment dans `Mon profil.txt`, dans ton dossier Bobine : quelques lignes sur ce que tu fais et ce que tu cherches dans tes vidéos. Les lignes qui commencent par `#` sont ignorées. Les vidéos plus anciennes reçoivent leur mémo petit à petit, 10 par passage, sans toucher à leurs résumés.

### *Recommandé* : le raccourci iPhone (partager en un geste)

Sur ton iPhone, app **Raccourcis** (« Shortcuts ») :

1. **+** → ajoute l'action « **Append to Text File** » (cherche « append ») ;
2. dans le champ texte : insère la variable « **Shortcut Input** » ;
3. **File Path** : écris exactement `inbox.txt` (laisse l'emplacement « Shortcuts » sur iCloud Drive) ;
4. active l'option « **New Line** » si elle apparaît ;
5. ⓘ → active « **Show in Share Sheet** », type : URLs uniquement ;
6. nomme-le « **Send to Bobine** ».

Usage : dans Instagram/TikTok/YouTube → **Partager → Send to Bobine**. C'est tout.

### Demander à Bobine, depuis la page

Ouvre **Ma page**, puis **Demander**. Pose une question sur un sujet de ta bibliothèque, ou clique sur **Poser une question sur cette vidéo** dans une fiche. Bobine répond avec des liens vers les fiches utilisées. Aucune nouvelle clé : celle des résumés suffit.

Sur Mac, l'installation démarre la page sur ce Mac uniquement. Sur iPhone, le chat est disponible depuis l'adresse protégée de ton serveur Linux. Le fichier `vault.html` et sa copie iCloud restent en lecture seule : aucun bouton de chat inutilisable.

Bobine cherche localement puis envoie au service d'IA jusqu'à cinq fiches sous forme d'extraits, la question, le court historique et ton profil si tu en as écrit un. Il ne fait aucune recherche sur Internet. Si rien ne correspond, il le dit sans appel au service. Les liens permettent de vérifier la réponse, pas de garantir chaque affirmation.

La conversation reste dans l'onglet et n'est pas enregistrée sur disque. Le profil reste modifiable dans `Mon profil.txt` pour cette première version.

<details>
<summary>Limites et vérifications avancées</summary>

Une question à la fois, 10 demandes par minute et 100 sur 24 heures glissantes, par installation (y compris derrière un tunnel). Les tentatives admises comptent même en cas d'échec ou sans résultat. Un compteur privé ne conserve que des horodatages ; redémarrer ne remet pas le quota à zéro. Le contexte envoyé est plafonné à 16 000 caractères, la question à 2 000 caractères. La recherche repose sur les mots des fiches : essaie un sujet ou un nom précis.

Le serveur coupe une demande au bout de 60 secondes au maximum. Interrompre la connexion ne garantit pas que le fournisseur annule sa facturation. La clé reste côté serveur, jamais dans la page. Voir [le guide de vérification](docs/demander-verification.md).

</details>

### *Facultatif* : l'alternative dans le Terminal (Crush)

[Crush](https://charm.sh/crush) est un assistant qui vit dans le Terminal : léger, open source, sans compte à créer. Il utilise **la même clé API que tes résumés** : lancé dans le dossier de ton vault, il lit tes fiches pour répondre.

![Demander à sa collection : l'assistant lit tes fiches et répond](assets/capture-crush.png)

```bash
cd ~/Bobine    # le dossier de ton vault
crush
```

Puis pose tes questions en langage naturel : « Quelles vidéos parlent de cuisine ? », « Résume la vidéo sur le montage », « Quelles idées pour un post ? »… *(exemple dans l'image ci-dessus, sur un Bobine de démonstration.)*

*(L'installation prépare tout : le fichier `.crushrc` du dossier contient ta clé, le modèle DeepSeek et la lecture seule. Crush peut lire et chercher dans tes fiches, mais ses outils pour modifier des fichiers, lancer des commandes ou aller sur internet sont retirés. Pas encore installé ? `brew install charmbracelet/tap/crush` : le script d'installation te l'a proposé.)*

## Ton Bobine au quotidien

- **Sur le Mac** : **double-clique sur « Ma page »** dans le dossier de ton vault (ou ouvre `vault.html`) : recherche, pastilles de thèmes, liens vers les vidéos.
- **Sur l'iPhone** : Fichiers → iCloud Drive → **Bobine** → `vault.html` (mis à jour à chaque nouveau lot ; la carte du graphe reste sur le Mac).
- **Pour poser des questions** : ouvre **Ma page → Demander** sur Mac, ou la même page à l’adresse protégée de ton serveur. Crush reste une alternative facultative. La copie iCloud ne propose pas le chat.

## Importer un export Instagram

*Option avancée* : pour rattraper d'un coup des années de sauvegardes.

Si ton compte a des centaines (ou des milliers) de Reels gardés « pour plus tard », tout ingérer d'un coup serait des heures de transcription pour des fiches jamais relues. **`filtre.py` te laisse trier avant** : il lit ton export, applique tes règles, et seuls les posts retenus partent en transcription. Le tri suit **tes propres collections** : c'est ton rangement qui fait foi.

> 🛡️ **Côté compte, un risque faible** : l'export se demande via l'outil officiel d'Instagram ; `filtre.py` ne se connecte à rien (tout est local) ; et l'ingestion garde sa cadence douce habituelle (une vidéo à la fois, 15 par passage, 50 essais par jour). Aucun téléchargement automatique n'est sans risque, et c'est justement pour ça que ces limites existent.

**1.** Sur Instagram : **Paramètres → Centre des comptes → Vos informations et autorisations → Télécharger vos informations** (format **JSON**). Ça arrive par e-mail, parfois sous 48 h.

**2.** Décompresse l'archive et range-la quelque part à toi. Tu dois y voir `saved_posts.json` et `saved_collections.json`.

**3.** Dans le dossier de ton vault, génère ton fichier de tri, puis vérifie-le :

```bash
cd ~/Bobine     # le dossier de ton vault
.venv/bin/python filtre.py --export "CHEMIN/VERS/instagram-mon_compte" --init-config
.venv/bin/python filtre.py --export "CHEMIN/VERS/instagram-mon_compte" --rapport
```

`--init-config` écrit **`filtres.yaml`**, pré-rempli avec tes collections : ouvre-le et passe à `false` ce que tu ne veux pas voir atterrir (mèmes, pubs, citations…). `--rapport` montre le résultat de tes choix, motif par motif, avec des exemples, **sans rien lancer**. Les posts qu'aucune règle ne classe restent « à revoir » : jamais perdus, jamais ingérés par surprise.

**4.** Quand le rapport te plaît, produis la liste et lance la transcription (par lots, comme d'habitude) :

```bash
.venv/bin/python filtre.py --export "CHEMIN/VERS/instagram-mon_compte"
.venv/bin/python ingest.py liens-filtres.txt --vault . --cookies chrome --limite 10
.venv/bin/python enrichir.py --vault .     # résumés + pages
```

*(`filtres.yaml` reste chez toi : il n'est jamais publié. Tu peux aussi l'inspecter : `filtres.exemple.yaml` montre un fichier complet, commenté.)*

## Les coûts

| Brique | Coût |
|---|---|
| Téléchargement des vidéos (yt-dlp) | 0 € |
| Transcription (Whisper, en local) | 0 € |
| Sous-titres YouTube | 0 € |
| Résumés (ta clé API) | quelques centimes pour des centaines de vidéos |

## Dépannage : les classiques

- **Ta vidéo partagée n'est pas encore là ?** Attends jusqu'à 15 minutes avec ton Mac réveillé. Vérifie que tu as bien choisi « Send to Bobine » au moment du partage.
- **« Résumé en attente » ?** Ta vidéo est enregistrée. Le résumé est facultatif ; si tu l'as activé et que le service tarde, Bobine réessaie automatiquement.
- **La limite du jour est atteinte ?** Les nouvelles vidéos seront traitées demain. Les résumés des vidéos déjà enregistrées peuvent continuer aujourd'hui.

<details>
<summary>Dépannage avancé : journaux, réglages du fournisseur et commandes manuelles</summary>

- **Rien ne se passe après un partage** → regarde `logs/watch.log` (dernier passage + erreurs). Le réveil tourne toutes les 15 minutes, et rattrape au réveil du Mac.
- **Erreurs « yt-dlp »** → Instagram et YouTube changent souvent ; la mise à jour règle presque tout : `.venv/bin/pip install -U yt-dlp`
- **Un post ne passe jamais** → il est probablement supprimé ou privé (fréquent sur les vieilles sauvegardes) : Bobine ne le retente que 2 fois puis passe au suivant.
- **Des fiches restent « (résumé en attente) » alors que tu as une clé** → ouvre `logs/watch.log` : le message du fournisseur dit pourquoi (clé refusée, crédit épuisé, modèle retiré). Pour un modèle retiré, mets `API_MODEL=…` dans `config.env` ; Bobine réessaie à chaque passage.
- **Une fiche sans texte** → la vidéo n'a ni parole ni sous-titres (musique seule). La fiche gardera la description seulement.
- **Aucune alerte quand le réveil se bloque ?** Si la boîte iCloud devient illisible ~1 h, une notification macOS est envoyée automatiquement.
- **Relancer à la main** (pour un lot, ou après un import) :

```bash
cd ~/Bobine        # le dossier de ton vault (l'emplacement que tu as choisi)
.venv/bin/python ingest.py liens.txt --vault . --cookies chrome --limite 10
.venv/bin/python enrichir.py --vault .     # résumés + pages
```


</details>

## Désinstaller Bobine

Arrêter Bobine depuis le dossier de ta bibliothèque :

**Double-clique sur « Désinstaller Bobine.command »** (ou, en Terminal : `./desinstaller.sh`).

Il désactive les services automatiques de cette bibliothèque et propose de retirer la page iCloud. **Tes vidéos locales et tes autres fichiers restent en place.** Si tu n'en veux plus, vérifie le contenu du dossier puis supprime-le toi-même. Bobine ne supprime jamais automatiquement ta bibliothèque. *(Crush, l'assistant, est un outil à part : il reste installé si tu veux le garder. Et sur ton iPhone, tu peux supprimer le raccourci « Send to Bobine ».)*

## La structure du projet

Le dossier de ton vault (celui que tu as choisi à l'installation) ressemble à ceci :

```
Bobine/
├── ingest.py           # télécharge + transcrit → fiches (raw/)
├── filtre.py           # (option) choisit quoi ingérer depuis un export Instagram
├── demander.py         # questions, recherche locale et réponses sourcées
├── page_server.py      # page et chat, clé conservée côté serveur
├── enrichir.py         # résumés via ta clé API → index.md + pages
├── generate_page.py    # fabrique vault.html (lisible sans JavaScript) + la carte
├── graphe.py           # (héritage) liens [[Thèmes]] pour Obsidian
├── watch.sh            # le réveil : relève la boîte et enchaîne tout
├── install.sh          # installation guidée (environnement, réveil)
├── 👉 2. Installer Bobine.command   # double-clic : (ré)installe
├── desinstaller.sh     # arrête les services et conserve les fichiers locaux
├── Désinstaller Bobine.command # double-clic : désinstalle
├── requirements.txt    # dépendances Python
├── config.example.env  # à copier en config.env (clé API, réglages)
├── config.env          # TES réglages et ta clé API (privé, jamais dans le repo)
├── .crushrc            # réglages de Crush pour ce dossier (ta clé, lecture seule)
├── filtres.yaml        # (si tu importes) tes règles de tri, elles restent chez toi
├── LICENSE
├── raw/                # TES fiches (jamais dans le repo)
├── memos/              # le mémo de chaque vidéo (avec une clé API ; jamais dans le repo)
├── Mon profil.txt      # (facultatif) quelques lignes sur toi, pour « Pour toi »
├── journal.json        # ce qui a été traité (réussites, échecs, essais)
├── index.md            # l'index condensé (résumés + thèmes)
├── vault.html          # la page à consulter
├── Ma page.webloc      # double-clic : ouvre la page dans ton navigateur
├── graph.html          # la carte des thèmes
└── logs/               # journaux (watch.log)
```

## FAQ

**Et sur Windows ou Linux ?**
Windows : non. Bobine est pensé et testé pour Mac + iPhone, c'est un choix assumé. **Linux, oui** : une édition Linux/VPS complète existe (installeur, réveil systemd, page en HTTPS, boîte de réception locale) → **[linux/](linux/README.md)**. Même cœur, même licence, même philosophie : tout chez toi.

**Où vont mes données ?**
Bobine garde ta base de connaissances sur ta machine : aucun compte, aucun serveur à nous, aucune télémétrie. Quelques choses sortent de ta machine, toutes transparentes : le téléchargement des vidéos (Instagram, TikTok, YouTube, comme n'importe quel téléchargeur), avec les cookies de connexion de ton navigateur pour Instagram et TikTok seulement (sur Mac, Chrome par défaut : macOS peut demander une fois l'accès à « Chrome Safe Storage » ; à changer avec `COOKIES=…`) ; les téléchargements uniques des dépendances Python et du modèle de transcription ; et, uniquement si tu actives l'IA (résumés, questions à Crush), les textes concernés (transcriptions, fiches, tes questions, ton profil si tu l'as écrit) envoyés au fournisseur que tu as choisi (DeepSeek, OpenAI, OpenRouter…) avec ta propre clé API. Sur l'édition Mac, la page générée peut aussi être synchronisée via iCloud (proposé à l'installation, désactivable).

**Et si je ne mets pas de clé API ?**
Tout tourne très bien : chaque fiche est quand même créée avec sa transcription et sa description, dans `raw/`, et elle apparaît tout de suite dans ta page, marquée « résumé en attente ». Ajoute une clé quand tu veux : au passage suivant (dans les 15 minutes), Bobine remplace ces entrées par les vrais résumés et thèmes, automatiquement.

**En quoi c'est différent d'Obsidian ou Notion ?**
Ce n'est pas un remplaçant : Bobine **fabrique** ta bibliothèque. Les fiches sont de simples fichiers Markdown (`raw/`), que tu peux ouvrir avec n'importe quel outil, y compris Obsidian.

**Ça marche depuis quelles apps ?**
Instagram (Reels), TikTok et YouTube : des liens vers ces trois-là, partagés depuis ton iPhone ou collés n'importe où.

## Contribuer

Les retours et contributions sont bienvenus, le projet est resté simple exprès :

- **Un bug, une idée ?** → ouvre une [issue](https://github.com/wrouhli/bobine/issues).
- **Une correction ?** → une pull request directe, sans cérémonie (détails : [CONTRIBUTING.md](CONTRIBUTING.md)).
- **Une coquille dans la [version anglaise](README.md) ?** → bienvenue, dis-le en issue.

Et bien sûr : **une ⭐ sur le repo** aide d'autres personnes à découvrir Bobine.

## Auteur

Créé et maintenu par **[Wahid Rouhli](https://www.wahidrouhli.com/)**.

## Licence

MIT : voir `LICENSE`.
Merci aussi à [yt-dlp](https://github.com/yt-dlp/yt-dlp), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [gallery-dl](https://github.com/mikf/gallery-dl) et [Charm](https://charm.sh).
