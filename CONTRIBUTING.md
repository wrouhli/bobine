# Contribuer à Bobine

Merci de vouloir aider ! 🎞️ Quelques principes simples pour que ça reste agréable.

## L'esprit

Bobine est fait pour **Monsieur et Madame Tout-le-Monde** : messages d'interface en français clair, zéro jargon, zéro dépendance inutile. Une fonctionnalité qui complique l'installation ou qui demande un compte en ligne a peu de chances d'être acceptée.

## Proposer quelque chose

- **Un bug** (une vidéo qui ne passe pas, un message bizarre) → ouvre une issue avec : ce que tu as fait, ce qui s'est passé, et si possible les 20 dernières lignes de `logs/watch.log`.
- **Une idée** → ouvre une issue aussi, en expliquant *pour qui* c'est utile.
- **Du code** → pull request directe, c'est le plus simple. Décris juste pourquoi.

## Le style du code

- Python simple, bibliothèque standard d'abord. Pas de framework.
- Le code, les commentaires et les messages s'écrivent en français.
- Les scripts doivent continuer à fonctionner quand une clé API est absente.

## Les règles d'or

- **Aucune donnée personnelle** dans le repo (fiches, logs, journaux, clés…).
- **Jamais de secret** commité (clé API, tokens).
- Garde les garde-fous existants (limites de téléchargement, retries) : ils protègent les utilisateurs.

## Tester avant d'envoyer

Le plus simple : un dossier vide, un clone dedans, et tu lances `./install.sh` : Bobine sait s'installer en bac à sable. Sur le repo de travail : `.venv/bin/python enrichir.py --dry-run` pour un test rapide.

## Lancer les tests

Aucune dépendance à installer (bibliothèque standard uniquement) :

    python3 -m unittest discover -s tests

Ils couvrent le nettoyage des sous-titres (SRT/VTT), l'extraction des identifiants et la forme canonique des liens, la sûreté des noms de fichiers, le journal (reprise d'un fichier abîmé), les résumés (mode sans clé, échecs du service, réponses piégées), les pages (liens sûrs, repères, index piégé), la lecture de `config.env` par les scripts shell, et le filtre d'import (`filtre.py` : export Instagram, filtres.yaml, classement). Chaque pull request les lance automatiquement (GitHub Actions, Python 3.10 et 3.12). Si tu as `pytest`, `pytest tests/` fonctionne aussi.

L'**édition Linux** (`linux/`) a sa suite à côté :

    python3 -m unittest discover -s linux/tests

Vérifie aussi `shellcheck -S warning` sur les scripts shell et `ruff check --select F,B` sur le Python avant d'envoyer (`pip install ruff`). Ces contrôles passent localement ; leur ajout à la CI est proposé dans la PR d'audit.

La CI lance les deux suites, et vérifie que les fichiers du cœur partagé (ingestion, enrichir, pages, tests communs…) restent **identiques au bit près** entre la racine et `linux/` : un garde-fou contre la dérive.

Merci ! 🙏
