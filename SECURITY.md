# Sécurité

## Signaler une vulnérabilité

Bobine est un outil **100 % local** : pas de serveur à nous, pas de compte, pas de télémétrie. Les risques concernent surtout ta machine, ton vault, et les briques que tu exposes volontairement (page servie à distance, serveur de liens).

Si tu penses avoir trouvé un problème de sécurité, merci de **ne pas ouvrir d'issue publique** :

- utilise le [signalement privé GitHub](https://github.com/wrouhli/bobine/security/advisories/new) (onglet Security → Report a vulnerability) ;
- ou contacte l'auteur, [@wrouhli](https://github.com/wrouhli).

On te répondra rapidement, avec un crédit si tu le souhaites.

## Périmètre

Concernent le dépôt : `ingest.py`, `enrichir.py`, `filtre.py`, `generate_page.py`, `graphe.py`, `watch.sh`, `install.sh`, `desinstaller.sh`, et l'édition `linux/` (y compris les petits serveurs optionnels `inbox_server.py` et `page_server.py`).

Hors périmètre : les dépendances (yt-dlp, faster-whisper, gallery-dl, Crush…), à signaler à leurs projets respectifs ; et toute exposition volontaire d'un service sans mot de passe ni videur en amont.

## Versions

Seule la dernière [release](https://github.com/wrouhli/bobine/releases) (et la branche `main`) sont supportées.
