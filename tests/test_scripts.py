#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests des scripts shell — lecture de config.env sans l'exécuter.

Lancement (aucune dépendance à installer, bash requis) :

    python3 -m unittest discover -s tests
"""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = next((RACINE / nom for nom in ("watch.sh", "watch-linux.sh")
               if (RACINE / nom).is_file()), None)


@unittest.skipIf(SCRIPT is None or shutil.which("bash") is None, "bash ou script absent")
class LectureConfig(unittest.TestCase):
    """lire_config_env : les valeurs sont lues, jamais exécutées."""

    def _fonction(self):
        texte = SCRIPT.read_text(encoding="utf-8")
        trouve = re.search(r"^lire_config_env\(\) \{.*?^\}\n", texte, re.S | re.M)
        self.assertIsNotNone(trouve, "fonction lire_config_env introuvable")
        return trouve.group(0)

    def test_valeurs_lues_sans_execution(self):
        with tempfile.TemporaryDirectory() as dossier:
            temoin = Path(dossier) / "execute"
            config = Path(dossier) / "config.env"
            config.write_text(
                "# commentaire\n"
                "NOM=Ma Bobine\n"
                'VAULT="$HOME/Mon Bobine"\n'
                "COOKIES=chrome   # navigateur\n"
                "NOTIF_CMD='curl -d \"$NOTIF_MESSAGE\" https://ntfy.sh/x'\n"
                "INBOX=$(touch " + str(temoin) + ")\n"
                "PATH=/nulle-part\n", encoding="utf-8")
            code = (self._fonction()
                    + 'HOME=/maison; lire_config_env "' + str(config) + '" VAULT INBOX COOKIES NOM NOTIF_CMD\n'
                    + 'printf "%s|%s|%s|%s|%s|%s" "$NOM" "$VAULT" "$COOKIES" "$NOTIF_CMD" "$INBOX" "$PATH"\n')
            sortie = subprocess.run(["bash", "-c", code], capture_output=True, text=True).stdout
            self.assertFalse(temoin.exists(), "une valeur a été exécutée")
        nom, vault, cookies, notif, inbox, chemin = sortie.split("|")
        self.assertEqual(nom, "Ma Bobine")
        self.assertEqual(vault, "/maison/Mon Bobine")
        self.assertEqual(cookies, "chrome")
        self.assertEqual(notif, 'curl -d "$NOTIF_MESSAGE" https://ntfy.sh/x')
        self.assertEqual(inbox, "$(touch " + str(Path(dossier) / "execute") + ")")
        self.assertNotEqual(chemin, "/nulle-part")


if __name__ == "__main__":
    unittest.main()
