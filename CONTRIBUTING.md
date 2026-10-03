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
- Garde les garde-fous existants (limites de téléchargement, retries) — ils protègent les utilisateurs.

## Tester avant d'envoyer

Le plus simple : un dossier vide, un clone dedans, et tu lances `./install.sh` — Bobine sait s'installer en bac à sable. Sur le repo de travail : `.venv/bin/python enrichir.py --dry-run` pour un test rapide.

Merci ! 🙏
