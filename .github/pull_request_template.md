## Quoi ?

Décris en une ou deux phrases ce que fait cette pull request.

## Pourquoi ?

Le contexte, le souci réglé, le lien vers l'issue (ex. « Fixes #12 »).

## Checklist

- [ ] `python3 -m unittest discover -s tests` passe (et `-s linux/tests` si tu touches à l'édition Linux)
- [ ] Si le cœur partagé a changé : la racine et `linux/` sont restés identiques au bit près (la CI le vérifie)
- [ ] Aucune donnée personnelle ni secret dans le commit
- [ ] Changement visible ? Une capture ou un avant/après, c'est parfait
