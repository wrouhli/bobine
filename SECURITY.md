# Sécurité

## Signaler une vulnérabilité

Bobine est un outil **local-first** : pas de serveur à nous, pas de compte, pas de télémétrie. Les risques concernent surtout ta machine, ton vault, et les briques que tu exposes volontairement (page servie à distance, serveur de liens).

Si tu penses avoir trouvé un problème de sécurité, merci de **ne pas ouvrir d'issue publique** :

- utilise le [signalement privé GitHub](https://github.com/wrouhli/bobine/security/advisories/new) (onglet Security → Report a vulnerability) ;
- ou contacte l'auteur, [@wrouhli](https://github.com/wrouhli).

On te répondra rapidement, avec un crédit si tu le souhaites.

## Périmètre

Concernent le dépôt : `ingest.py`, `enrichir.py`, `filtre.py`, `generate_page.py`, `graphe.py`, `watch.sh`, `install.sh`, `desinstaller.sh`, et l'édition `linux/` (y compris les petits serveurs optionnels `inbox_server.py` et `page_server.py`).

Hors périmètre : les dépendances (yt-dlp, faster-whisper, gallery-dl, Crush…), à signaler à leurs projets respectifs ; et toute exposition volontaire d'un service sans mot de passe ni videur en amont.

## Versions

Seule la dernière [release](https://github.com/wrouhli/bobine/releases) (et la branche `main`) sont supportées.

---

## Security policy (English)

Bobine is **local-first**: no server of ours, no account, no telemetry. Risks mainly concern your machine, your vault, and the pieces you choose to expose (the remote page, the link server).

**Please do not open a public issue for a vulnerability.** Use [GitHub private reporting](https://github.com/wrouhli/bobine/security/advisories/new) (Security tab, then "Report a vulnerability"), or contact [@wrouhli](https://github.com/wrouhli). You will get a quick answer, and credit if you wish.

**In scope:** `ingest.py`, `enrichir.py`, `filtre.py`, `generate_page.py`, `graphe.py`, `watch.sh`, `install.sh`, `desinstaller.sh`, and the `linux/` edition (including the optional `inbox_server.py` and `page_server.py`). Content coming from videos or from the AI model that ends up in the pages is in scope too.

**Out of scope:** dependencies (yt-dlp, faster-whisper, gallery-dl, Crush…), to be reported to their own projects, and any service deliberately exposed without a password or upstream protection.

**Supported versions:** only the latest [release](https://github.com/wrouhli/bobine/releases) and the `main` branch.
