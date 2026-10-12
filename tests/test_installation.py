#!/usr/bin/env python3
"""Installation safety regressions, using only stdlib, bash and temporary homes.

Run: python3 -m unittest discover -s tests -p test_installation.py -v
Uninstallers run in full. Installer selection/copy and config sections run in
isolation, so dependency installation and real background services never run.
"""

import os
import plistlib
import shlex
import sys
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLERS = ("install.sh", "linux/install-linux.sh")
UNINSTALLERS = ("desinstaller.sh", "linux/desinstaller-linux.sh")
REFUSAL = (
    "Ce dossier contient déjà des fichiers. "
    "Choisis un dossier vide pour les protéger."
)


def snapshot(root):
    """Record names, contents, symlink targets, permissions and modification times."""
    result = {}
    for path in [root, *root.rglob("*")]:
        info = path.lstat()
        if path.is_symlink():
            content = os.readlink(path)
        elif path.is_file():
            content = path.read_bytes()
        else:
            content = None
        result[str(path.relative_to(root))] = (
            stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode),
            info.st_mtime_ns, content,
        )
    return result


@unittest.skipIf(shutil.which("bash") is None, "bash required")
class InstallationSafety(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bobine-installation-")
        self.addCleanup(temporary.cleanup)
        # Chemin réel : sur macOS, /var est un lien vers /private/var. Les cas de
        # liens symboliques sont testés explicitement, pas par accident.
        self.sandbox = Path(temporary.name).resolve()
        self.home = self.sandbox / "home"
        self.home.mkdir()
        self.bin = self.sandbox / "bin"
        self.bin.mkdir()
        self.calls = self.sandbox / "service-calls"
        self.env = os.environ.copy()
        self.env.update(
            HOME=str(self.home),
            PATH=str(self.bin) + os.pathsep + os.defpath,
            CALL_LOG=str(self.calls),
            # Le python3 d'Apple écrirait sinon son cache dans ~/Library/Caches.
            PYTHONDONTWRITEBYTECODE="1",
        )
        for command in ("launchctl", "systemctl"):
            stub = self.bin / command
            stub.write_text(
                '#!/bin/bash\n'
                f'printf "{command} %s\\n" "$*" >> "$CALL_LOG"\n'
                'exit 0\n', encoding="utf-8",
            )
            stub.chmod(0o755)

    def run_bash(self, args, answers=""):
        result = subprocess.run(
            [shutil.which("bash"), *map(str, args)],
            input=answers, capture_output=True, text=True,
            env=self.env, cwd=self.sandbox, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def make_vault(self, name):
        vault = self.home / Path(name).stem
        vault.mkdir()
        shutil.copy2(ROOT / name, vault / Path(name).name)
        files = {
            "watch.sh": "#!/bin/bash\n",
            "watch-linux.sh": "#!/bin/bash\n",
            "ingest.py": "# fixture only\n",
            "config.env": 'NOM="Bobine"\nPAGE_ORIGIN="https://bobine.example.org"\n',
            "LICENSE": "My private license, not Bobine's\n",
            "README.md": "Personal notes mentioning Bobine, not owned by it\n",
            "README.fr.md": "Mes notes Bobine\n",
            "README.en.md": "My Bobine notes\n",
            ".gitignore": "journal.json\nmy-private-data\n",
            "private data/secret.txt": "PRIVATE\n",
            "raw/family.mp4": "PRIVATE VIDEO\n",
            "logs/personal.log": "PRIVATE LOG\n",
            "tests/my_test.py": "# PRIVATE TEST\n",
            ".git/config": "# PRIVATE REPOSITORY\n",
            "journal.json": '{"personal": true}\n',
            "vault.html": "My local video page\n",
            "index.md": "My video index\n",
            "odd\nname.txt": "PRIVATE FILE\n",
        }
        for relative, content in files.items():
            path = vault / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        for module in ("enrichir.py", "ingest.py"):
            shutil.copy2(ROOT / module, vault / module)
        (vault / "private link").symlink_to("private data/secret.txt")
        return vault

    def assert_retained(self, output):
        self.assertIn("Bobine est arrêté", output)
        self.assertIn("Toutes tes vidéos locales et tes autres fichiers sont conservés.", output)
        self.assertIn("Après avoir vérifié son contenu", output)
        self.assertNotIn("➜", output, "local uninstall must not require deletion confirmation")
        self.assertNotIn("Pour confirmer", output)
        self.assertNotIn("corbeille", output)
        self.assertNotIn("est désinstallé", output)

    def test_uninstall_retains_every_local_file_without_confirmation(self):
        for name in UNINSTALLERS:
            with self.subTest(script=name):
                vault = self.make_vault(name)
                before = snapshot(vault)
                output = self.run_bash([vault / Path(name).name])
                self.assert_retained(output)
                self.assertEqual(snapshot(vault), before)
                self.assertFalse(self.calls.exists())

    def test_uninstall_cannot_delete_even_with_old_confirmation_answers(self):
        for name in UNINSTALLERS:
            with self.subTest(script=name):
                vault = self.make_vault(name)
                before = snapshot(vault)
                output = self.run_bash([vault / Path(name).name], "o\nsupprimer\n")
                self.assert_retained(output)
                self.assertEqual(snapshot(vault), before)

    def services(self, vault, matching):
        target = vault if matching else self.home / "another-vault"
        if (vault / "desinstaller.sh").exists():
            directory = self.home / "Library/LaunchAgents"
            files = {"com.bobine.watch.plist": f"{target}/watch.sh\n"}
        else:
            directory = self.home / ".config/systemd/user"
            cloud = self.home / ".cloudflared"
            cloud.mkdir(exist_ok=True)
            (cloud / "bobine-page.yml").write_text(
                'ingress:\n  - hostname: "bobine.example.org"\n'
                '    service: http://127.0.0.1:8786\n  - service: http_status:404\n')
            files = {
                "bobine-watch.service": f"[Service]\nExecStart=/bin/bash {target}/watch-linux.sh\n",
                "bobine-watch.timer": "Timer\n",
                "bobine-watch.path": "Path\n",
                "bobine-inbox.service": f"[Service]\nExecStart=/usr/bin/python3 {target}/inbox_server.py --vault {target}\n",
                "bobine-page.service": f"[Service]\nExecStart=/usr/bin/python3 {target}/page_server.py --vault {target}\n",
                "bobine-tunnel.service": '[Service]\nExecStart=/usr/local/bin/cloudflared --no-autoupdate tunnel '
                                         '--config %h/.cloudflared/bobine-page.yml run\n',
            }
        directory.mkdir(parents=True)
        for name, content in files.items():
            (directory / name).write_text(content, encoding="utf-8")
        return directory

    def test_uninstall_disables_only_matching_services_and_keeps_data(self):
        for name in UNINSTALLERS:
            with self.subTest(script=name):
                vault = self.make_vault(name)
                before = snapshot(vault)
                directory = self.services(vault, matching=True)
                output = self.run_bash([vault / Path(name).name])
                self.assert_retained(output)
                self.assertEqual(snapshot(vault), before)
                self.assertEqual(list(directory.iterdir()), [])
                calls = self.calls.read_text(encoding="utf-8")
                if name == "desinstaller.sh":
                    self.assertIn("launchctl bootout gui/", calls)
                    self.assertIn("/com.bobine.watch", calls)
                else:
                    for units in (
                        "bobine-watch.timer", "bobine-watch.path",
                        "bobine-inbox.service", "bobine-page.service bobine-tunnel.service",
                    ):
                        self.assertIn(f"systemctl --user disable --now {units}\n", calls)
                    self.assertIn("systemctl --user daemon-reload", calls)
                self.calls.unlink()

    def test_uninstall_leaves_another_vault_services_untouched(self):
        for name in UNINSTALLERS:
            with self.subTest(script=name):
                vault = self.make_vault(name)
                before = snapshot(vault)
                directory = self.services(vault, matching=False)
                services_before = snapshot(directory)
                self.run_bash([vault / Path(name).name])
                self.assertEqual(snapshot(vault), before)
                self.assertEqual(snapshot(directory), services_before)
                self.assertFalse(self.calls.exists())

    def test_uninstall_ne_confond_pas_dossiers_au_meme_prefixe(self):
        vault = self.make_vault("linux/desinstaller-linux.sh")
        directory = self.services(vault, matching=True)
        for file in directory.glob("*.service"):
            file.write_text(file.read_text().replace(str(vault), str(vault) + "-autre"))
        before = snapshot(directory)
        self.run_bash([vault / "desinstaller-linux.sh"])
        self.assertEqual(snapshot(directory), before)
        self.assertFalse(self.calls.exists())

    def test_icloud_prompt_is_optional_and_does_not_affect_local_files(self):
        vault = self.make_vault("desinstaller.sh")
        before = snapshot(vault)
        cloud = self.home / "Library/Mobile Documents/com~apple~CloudDocs/Bobine"
        cloud.mkdir(parents=True)
        page = cloud / "vault.html"
        page.write_text("iCloud page", encoding="utf-8")
        private = cloud / "private.txt"
        private.write_text("private cloud data", encoding="utf-8")
        cloud_before = snapshot(cloud)
        output = self.run_bash([vault / "desinstaller.sh"], "n\n")
        self.assertIn("la copie iCloud reste en place", output)
        self.assertNotIn("réveil et copie iCloud retirés", output)
        self.assertEqual(snapshot(cloud), cloud_before)
        self.assertEqual(snapshot(vault), before)
        output = self.run_bash([vault / "desinstaller.sh"], "o\n")
        self.assertIn("La page est retirée", output)
        self.assertFalse(page.exists())
        self.assertEqual(private.read_text(encoding="utf-8"), "private cloud data")
        self.assertEqual(snapshot(vault), before)
        self.assertIn("tes fichiers locaux sont conservés", output)

    def installer_harness(self, name, config=False):
        """Execute actual selection/copy and (optionally) config shell sections."""
        text = (ROOT / name).read_text(encoding="utf-8")
        helpers = text[text.index("if [ -t 1 ]; then"):
                       text.index("# ------------------------------------------------------------------- bannière")]
        selection = text.split("# ---------------------------------------------------------------- 3. emplacement\n", 1)[1]
        selection = selection.split("# ------------------------------------------------", 1)[0]
        code = 'set -u\nDEPOT="$1"\nSCRIPT_DIR="$DEPOT"\nNOM_VAULT="Bobine"\n'
        code += helpers + selection
        if config:
            configuration = text.split("# ---------------------------------------------------------------- 4. clé API\n", 1)[1]
            end = ("# ---------------------------------------------------------------- réveil (launchd)"
                   if name == "install.sh" else "# ---------------------------------------------------------------- 6. dépendances")
            code += configuration.split(end, 1)[0]
        return code + '\nprintf "\\nTARGET=%s\\n" "$CIBLE"\n'

    def make_depot(self, name):
        depot = self.sandbox / ("depot-" + Path(name).stem)
        depot.mkdir()
        (depot / "LICENSE").write_text("fixture license\n", encoding="utf-8")
        (depot / "ingest.py").write_text("# fixture core\n", encoding="utf-8")
        # Le dépôt livre toujours page-locale.sh : l'installateur le charge au départ.
        shutil.copy2((ROOT / name).parent / "page-locale.sh", depot / "page-locale.sh")
        return depot

    def run_installer(self, name, depot, answers, config=False):
        return self.run_bash(
            ["-c", self.installer_harness(name, config), "installer-fixture", depot],
            answers,
        )

    def test_install_refuses_nonempty_targets_without_override(self):
        for name in INSTALLERS:
            with self.subTest(script=name):
                depot = self.make_depot(name)
                foreign = self.home / ("foreign-" + Path(name).stem)
                foreign.mkdir()
                (foreign / "ingest.py").write_text("private core\n", encoding="utf-8")
                (foreign / "LICENSE").write_text("private license\n", encoding="utf-8")
                (foreign / "README.md").write_text("personal notes\n", encoding="utf-8")
                before = snapshot(foreign)
                empty = self.home / ("empty-" + Path(name).stem)
                output = self.run_installer(name, depot, f"{foreign}\no\n{empty}\n")
                self.assertIn(REFUSAL, output)
                self.assertNotIn("Installer dedans quand même", output)
                self.assertIn(f"TARGET={empty}", output)
                self.assertEqual(snapshot(foreign), before)
                self.assertEqual((empty / "LICENSE").read_bytes(), (depot / "LICENSE").read_bytes())

    def test_install_refuses_hidden_only_or_newline_named_files(self):
        for name in INSTALLERS:
            depot = self.make_depot(name)
            for index, filename in enumerate((".git", "\n")):
                with self.subTest(script=name, filename=filename):
                    foreign = self.home / f"foreign-{Path(name).stem}-{index}"
                    foreign.mkdir()
                    (foreign / filename).write_text("private", encoding="utf-8")
                    before = snapshot(foreign)
                    empty = self.home / f"empty-{Path(name).stem}-{index}"
                    output = self.run_installer(name, depot, f"{foreign}\n{empty}\n")
                    self.assertIn(REFUSAL, output)
                    self.assertIn(f"TARGET={empty}", output)
                    self.assertEqual(snapshot(foreign), before)

    def test_install_refuses_symlink_to_foreign_directory(self):
        for name in INSTALLERS:
            with self.subTest(script=name):
                depot = self.make_depot(name)
                foreign = self.home / ("foreign-" + Path(name).stem)
                foreign.mkdir()
                (foreign / "private.txt").write_text("private", encoding="utf-8")
                before = snapshot(foreign)
                alias = self.home / ("alias-" + Path(name).stem)
                alias.symlink_to(foreign, target_is_directory=True)
                empty = self.home / ("empty-" + Path(name).stem)
                output = self.run_installer(name, depot, f"{alias}\n{empty}\n")
                self.assertIn(REFUSAL, output)
                self.assertIn(f"TARGET={empty}", output)
                self.assertEqual(snapshot(foreign), before)
                self.assertTrue(alias.is_symlink())

    def test_install_allows_in_place_reinstall_without_copying_core(self):
        for name in INSTALLERS:
            with self.subTest(script=name):
                depot = self.make_depot(name)
                (depot / "config.env").write_text('NOM="Bobine"\n', encoding="utf-8")
                (depot / "README.md").write_text("personal notes", encoding="utf-8")
                before = snapshot(depot)
                output = self.run_installer(name, depot, f"{depot}\n")
                self.assertNotIn(REFUSAL, output)
                self.assertIn(f"TARGET={depot}", output)
                self.assertEqual(snapshot(depot), before)

    def test_openai_choice_generates_key_and_model_without_extra_question(self):
        for name in INSTALLERS:
            with self.subTest(script=name):
                depot = self.make_depot(name)
                target = self.home / ("openai-" + Path(name).stem)
                answers = f"{target}\no\n2\nsk-test-only\nn\nn\n"
                if name == "install.sh":
                    answers += "n\n"  # iCloud option
                output = self.run_installer(name, depot, answers, config=True)
                config = target / "config.env"
                lines = config.read_text(encoding="utf-8").splitlines()
                self.assertIn("OPENAI_API_KEY=sk-test-only", lines)
                self.assertIn("API_MODEL=gpt-4o-mini", lines)
                self.assertEqual(sum(line.startswith("API_MODEL=") for line in lines), 1)
                self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
                self.assertNotIn("Identifiant du modèle", output)
                self.assertNotIn("sk-test-only", output)
                self.assertFalse((target / ".venv").exists())
                self.assertFalse(self.calls.exists())


    def run_profile_block(self, name, folder, answers):
        """Execute only the installer's optional profile question, in `folder`."""
        text = (ROOT / name).read_text(encoding="utf-8")
        helpers = text[text.index("if [ -t 1 ]; then"):
                       text.index("# ------------------------------------------------------------------- bannière")]
        block = text[text.index("# Profil (facultatif)"):text.index("# écrire config.env")]
        code = ("set -u\ncd \"$1\" || exit 1\nDEPOT=" + shlex.quote(str((ROOT / name).parent)) + "\n"
                + helpers + block)
        return self.run_bash(["-c", code, "profile-fixture", folder], answers)

    def test_profile_question_is_optional_and_never_overwrites(self):
        import sys
        sys.path.insert(0, str(ROOT))
        import enrichir
        for name in INSTALLERS:
            with self.subTest(script=name, case="answer"):
                folder = self.sandbox / ("profil-" + Path(name).stem)
                folder.mkdir()
                self.run_profile_block(name, folder, "Je forme des équipes à l'IA.\n")
                profile = folder / "Mon profil.txt"
                self.assertEqual(stat.S_IMODE(profile.stat().st_mode), 0o600)
                self.assertEqual(enrichir.lire_profil(folder), "Je forme des équipes à l'IA.")
            with self.subTest(script=name, case="skip"):
                folder = self.sandbox / ("sans-profil-" + Path(name).stem)
                folder.mkdir()
                self.run_profile_block(name, folder, "\n")
                self.assertTrue((folder / "Mon profil.txt").exists())
                self.assertEqual(enrichir.lire_profil(folder), "")
            with self.subTest(script=name, case="keep"):
                folder = self.sandbox / ("garde-" + Path(name).stem)
                folder.mkdir()
                (folder / "Mon profil.txt").write_text("Mon texte à moi\n", encoding="utf-8")
                output = self.run_profile_block(name, folder, "Autre chose\n")
                self.assertEqual((folder / "Mon profil.txt").read_text(encoding="utf-8"), "Mon texte à moi\n")
                self.assertIn("Profil conservé", output)


    def test_install_copies_shared_page_modules_and_preserves_modes(self):
        for name in INSTALLERS:
            with self.subTest(script=name):
                depot = self.make_depot(name)
                for module in ("page_server.py", "demander.py"):
                    (depot / module).write_text("# fixture " + module + "\n")
                    (depot / module).chmod(0o755)
                target = self.home / ("modules-" + Path(name).stem)
                self.run_installer(name, depot, f"{target}\n")
                for module in ("page_server.py", "demander.py"):
                    self.assertEqual((target / module).read_bytes(), (depot / module).read_bytes())
                    self.assertTrue((target / module).stat().st_mode & stat.S_IXUSR)

    def test_reinstall_preserves_page_config_without_executing_it(self):
        for name in INSTALLERS:
            with self.subTest(script=name):
                depot = self.make_depot(name)
                sentinel = self.sandbox / "config-executed"
                settings = ('PAGE_PASSWORD="secret personnel"\n'
                            'PAGE_ORIGIN="https://bobine.example.org"\n'
                            'INBOX_TOKEN="token-personnel"\n'
                            # Choix précédent de Demander : repris pour le défaut de la dernière question.
                            'DEMANDER=non\n'
                            f'NOTIF_CMD="$(touch {sentinel})"\n')
                (depot / "config.env").write_text('NOM="Bobine"\n' + settings)
                (depot / "Mon profil.txt").write_text("Profil personnel\n")
                before = snapshot(depot / "Mon profil.txt")
                self.run_installer(name, depot, f"{depot}\nn\nn\nn\nn\n", config=True)
                config = (depot / "config.env").read_text()
                for line in settings.splitlines():
                    self.assertIn(line, config)
                self.assertFalse(sentinel.exists())
                self.assertEqual(snapshot(depot / "Mon profil.txt"), before)
                self.assertEqual(stat.S_IMODE((depot / "config.env").stat().st_mode), 0o600)
                self.assertFalse(self.calls.exists())

    # Scripts partagés de la page locale, copiés par les installateurs.
    DEMANDER_SCRIPTS = ("page-locale.sh", "activer-demander.sh", "desactiver-demander.sh", "ouvrir-ma-page.sh")

    def stub(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)
        return path

    def mac_stubs(self):
        """launchd, sonde HTTP, navigateur et compilateur AppleScript : tous simulés.

        Aucun service réel, aucune connexion : curl simule la sonde de
        127.0.0.1:8786 d'après l'état fictif du service (fichiers dans HOME).
        """
        self.opened = self.sandbox / "opened"
        self.env["OPEN_LOG"] = str(self.opened)
        self.stub("sleep", "#!/bin/bash\nexit 0\n")
        self.stub("launchctl",
                  '#!/bin/bash\nprintf "launchctl %s\\n" "$*" >> "$CALL_LOG"\n'
                  'case "$1" in\n'
                  ' print) if [ -e "$HOME/page-loaded" ]; then\n'
                  '   printf "state = %s\\npid = 12345\\n" "${PAGE_STATE:-running}"; exit 0\n'
                  '   elif [ "${UNMANAGED_SERVICE:-0}" = 1 ]; then exit 0; else exit 1; fi ;;\n'
                  ' bootstrap) [ "${BOOTSTRAP_FAIL:-0}" = 1 ] && exit 1; touch "$HOME/page-loaded" ;;\n'
                  ' bootout) rm -f "$HOME/page-loaded" "$HOME/page-stopped" ;;\n'
                  ' kickstart) [ "${KICKSTART_FAIL:-0}" = 1 ] && exit 1; rm -f "$HOME/page-stopped" ;;\n'
                  'esac\nexit 0\n')
        self.stub("curl",
                  '#!/bin/bash\n'
                  'if [ -e "$HOME/page-loaded" ] && [ ! -e "$HOME/page-stopped" ] && [ "${HEALTH_FAIL:-0}" != 1 ]; then\n'
                  '  printf "ok\\n\\n200"; exit 0\nfi\n'
                  'if [ "${PORT_OCCUPE:-0}" = 1 ] || [ -e "$HOME/page-loaded" ]; then printf "autre\\n404"; exit 0; fi\n'
                  'exit 7\n')
        self.stub("open", '#!/bin/bash\nprintf "%s\\n" "$*" >> "$OPEN_LOG"\n')
        # Par défaut, pas de compilateur AppleScript : repli « Ma page.webloc ».
        self.stub("osacompile", "#!/bin/bash\nexit 1\n")
        self.stub("codesign", "#!/bin/bash\nexit 0\n")

    def osacompile_stub(self):
        """Crée un paquet .app minimal et garde le script AppleScript reçu."""
        self.stub("osacompile",
                  '#!/bin/bash\nsortie=""; source_as=""\n'
                  'while [ $# -gt 0 ]; do\n'
                  '  case "$1" in -o) sortie="$2"; shift 2 ;; -e) source_as="$source_as$2\n"; shift 2 ;; *) shift ;; esac\n'
                  'done\n'
                  'mkdir -p "$sortie/Contents/Resources/Scripts" "$sortie/Contents/MacOS"\n'
                  'printf "%s" "$source_as" > "$sortie/Contents/Resources/Scripts/main.scpt"\n'
                  'printf "osacompile %s\\n" "$sortie" >> "$CALL_LOG"\n')

    def page_fixture(self):
        vault = self.home / 'Bobine & <amis> "chez moi"'
        vault.mkdir()
        (vault / ".venv/bin").mkdir(parents=True)
        # Never executed as a service: launchctl and both network probes are stubs.
        (vault / ".venv/bin/python").symlink_to(sys.executable)
        for file in ("page_server.py", "demander.py", "vault.html"):
            (vault / file).write_text("fixture only\n")
        for module in ("generate_page.py", "enrichir.py", "ingest.py"):
            shutil.copy2(ROOT / module, vault / module)
        for script in self.DEMANDER_SCRIPTS:
            shutil.copy2(ROOT / script, vault / script)
        (vault / "config.env").write_text(
            f'X="$(touch {self.sandbox / "executed"})"\nSYNC_ICLOUD=non\nCARTE=non\n')
        self.mac_stubs()
        return vault

    def run_any(self, args, answers="", env=None):
        """Comme run_bash, sans exiger un code de retour nul : (code, sortie)."""
        result = subprocess.run(
            [shutil.which("bash"), *map(str, args)],
            input=answers, capture_output=True, text=True,
            env=env or self.env, cwd=self.sandbox, timeout=20,
        )
        return result.returncode, result.stdout + result.stderr

    def run_page(self, vault):
        # Ancien bloc « page locale » d'install.sh : désormais activer-demander.sh
        # (mêmes fonctions, partagées dans page-locale.sh).
        return self.run_any([vault / "activer-demander.sh"])[1]

    def page_plist(self, vault, target=None, effective=None):
        target = target or vault
        path = self.home / "Library/LaunchAgents/com.bobine.page.plist"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"Label": "com.bobine.page", "ProgramArguments": [
            str(target / ".venv/bin/python"), str(target / "page_server.py"),
            "--vault", str(effective or target), "--local"]}
        path.write_bytes(plistlib.dumps(data))
        return path

    def shortcut_url(self, vault):
        return plistlib.loads((vault / "Ma page.webloc").read_bytes())["URL"]

    def test_mac_page_has_safe_arguments_is_local_and_idempotent_without_key(self):
        vault = self.page_fixture()
        self.run_page(vault)
        plist = self.home / "Library/LaunchAgents/com.bobine.page.plist"
        data = plistlib.loads(plist.read_bytes())
        self.assertEqual(data["ProgramArguments"], [str(vault / ".venv/bin/python"),
                         str(vault / "page_server.py"), "--vault", str(vault), "--local"])
        self.assertEqual(data["WorkingDirectory"], str(vault))
        self.assertEqual(self.shortcut_url(vault), "http://127.0.0.1:8786/")
        self.assertFalse(self.sandbox.joinpath("executed").exists())
        first = plist.read_bytes()
        self.run_page(vault)
        self.assertEqual(plist.read_bytes(), first)
        self.assertEqual(self.shortcut_url(vault), "http://127.0.0.1:8786/")
        self.assertNotIn("watch", self.calls.read_text())
        self.assertNotIn("--bind", str(data))
        self.assertNotIn("--password", str(data))

    def test_mac_page_failed_start_uses_file_fallback(self):
        for variable in ("BOOTSTRAP_FAIL", "HEALTH_FAIL", "PAGE_STATE", "PORT_OCCUPE"):
            with self.subTest(failure=variable):
                # One isolated home per failure to avoid stale launchd fixture state.
                vault = self.page_fixture()
                self.env[variable] = "waiting" if variable == "PAGE_STATE" else "1"
                (vault / "Ma page.webloc").write_bytes(plistlib.dumps({"URL": "http://127.0.0.1:8786/"}))
                output = self.run_page(vault)
                self.assertIn("n'a pas démarré", output)
                self.assertEqual(self.shortcut_url(vault), (vault / "vault.html").as_uri())
                self.assertFalse((self.home / "page-loaded").exists())
                del self.env[variable]
                shutil.rmtree(vault)
                plist = self.home / "Library/LaunchAgents/com.bobine.page.plist"
                if plist.exists():
                    plist.unlink()

    def test_mac_page_keeps_file_fallback_intact_when_modules_are_missing(self):
        vault = self.page_fixture()
        (vault / "demander.py").unlink()
        shortcut = vault / "Ma page.webloc"
        shortcut.write_bytes(plistlib.dumps({"URL": (vault / "vault.html").as_uri()}))
        before = snapshot(shortcut)
        self.run_page(vault)
        self.assertEqual(snapshot(shortcut), before)
        self.assertFalse(self.calls.exists())

    def test_mac_uninstall_understands_xml_escaped_paths_and_leaves_watch_alone(self):
        vault = self.page_fixture()
        shutil.copy2(ROOT / "desinstaller.sh", vault / "desinstaller.sh")
        (vault / "watch.sh").write_text("# fixture\n")
        plist = self.page_plist(vault)
        before = snapshot(vault)
        self.run_bash([vault / "desinstaller.sh"])
        self.assertEqual(snapshot(vault), before)
        self.assertFalse(plist.exists())
        self.assertIn("/com.bobine.page", self.calls.read_text())
        self.assertNotIn("watch", self.calls.read_text())

    def test_mac_page_refuses_foreign_prefix_malformed_and_linked_services(self):
        vault = self.page_fixture()
        plist = self.page_plist(vault, Path(str(vault) + "-autre"))
        for case in ("foreign", "malformed", "symlink"):
            with self.subTest(case=case):
                if case == "malformed":
                    plist.write_text("<plist><broken>\n")
                elif case == "symlink":
                    plist.unlink()
                    target = self.sandbox / "personal.plist"
                    target.write_text("personal file\n")
                    plist.symlink_to(target)
                before = snapshot(plist)
                output = self.run_page(vault)
                self.assertIn("conservé", output)
                self.assertEqual(snapshot(plist), before)
                self.assertEqual(self.shortcut_url(vault), (vault / "vault.html").as_uri())
                self.assertFalse(self.calls.exists(), "must not touch another vault's service")

    def test_mac_page_refuses_loaded_unmanaged_service(self):
        vault = self.page_fixture()
        self.env["UNMANAGED_SERVICE"] = "1"
        self.run_page(vault)
        self.assertNotIn("bootout", self.calls.read_text())
        self.assertNotIn("bootstrap", self.calls.read_text())
        self.assertEqual(self.shortcut_url(vault), (vault / "vault.html").as_uri())

    def test_mac_page_preserves_personal_shortcut_and_symlink(self):
        vault = self.page_fixture()
        path = vault / "Ma page.webloc"
        for case in ("personal", "invalid", "symlink"):
            with self.subTest(case=case):
                if case == "personal":
                    path.write_bytes(plistlib.dumps({"URL": "https://my-own.example.org/"}))
                elif case == "invalid":
                    path.write_text("my own note, not a plist")
                else:
                    path.unlink()
                    target = self.sandbox / "personal.webloc"
                    target.write_text("personal shortcut")
                    path.symlink_to(target)
                before = snapshot(path)
                self.run_page(vault)
                self.assertEqual(snapshot(path), before)

    def test_mac_uninstall_through_symlink_stops_own_page_only(self):
        vault = self.make_vault("desinstaller.sh")
        lien = self.home / "Bobine-lien"
        lien.symlink_to(vault, target_is_directory=True)
        for own in (True, False):
            with self.subTest(own=own):
                cible = vault if own else Path(str(vault) + "-autre")
                plist = self.page_plist(vault, cible)
                before = snapshot(vault)
                if self.calls.exists():
                    self.calls.unlink()
                self.run_bash([lien / "desinstaller.sh"])
                self.assertEqual(snapshot(vault), before)
                if own:
                    self.assertFalse(plist.exists())
                    self.assertIn("/com.bobine.page", self.calls.read_text())
                else:
                    self.assertTrue(plist.exists())
                    self.assertFalse(self.calls.exists())

    def test_mac_uninstall_stops_exact_page_only_and_retains_secrets_profile(self):
        vault = self.make_vault("desinstaller.sh")
        for name in (".bobine-jeton", "Mon profil.txt", "demander.py", "page_server.py"):
            (vault / name).write_text("personal content\n")
        for matching in (False, True):
            with self.subTest(matching=matching):
                target = vault if matching else Path(str(vault) + "-autre")
                plist = self.page_plist(vault, target)
                before = snapshot(vault)
                self.run_bash([vault / "desinstaller.sh"])
                self.assertEqual(snapshot(vault), before)
                if matching:
                    self.assertFalse(plist.exists())
                    self.assertIn("/com.bobine.page", self.calls.read_text())
                    self.assertNotIn("watch", self.calls.read_text())
                else:
                    self.assertTrue(plist.exists())
                    self.assertFalse(self.calls.exists())

    def activation_fixture(self):
        vault = self.home / 'Linux espace & "citation" $argent %suite'
        vault.mkdir()
        (vault / "page_server.py").write_text("fixture only\n")
        (self.home / ".cloudflared").mkdir()
        (self.home / ".cloudflared/cert.pem").write_text("fixture cert\n")
        # Block all external commands; tests never contact Cloudflare or a server.
        stubs = {
            "cloudflared": '#!/bin/bash\nprintf "cloudflared %s\\n" "$*" >> "$CALL_LOG"\n'
                           'if [ "$1 $2" = "tunnel list" ]; then\n'
                           'echo "00000000-0000-0000-0000-000000000001 bobine-page"\nfi\nexit 0\n',
            "curl": '#!/bin/bash\nprintf "curl %s\\n" "$*" >> "$CALL_LOG"\nprintf 200\n',
            "sleep": '#!/bin/bash\nexit 0\n',
        }
        for name, content in stubs.items():
            (self.bin / name).write_text(content)
            (self.bin / name).chmod(0o755)
        return vault

    def run_activation(self, vault, host="bobine.example.org", success=True, options=None):
        result = subprocess.run(
            [shutil.which("bash"), str(ROOT / "linux/activer-page-web.sh"), host,
             "--vault", str(vault), *(options or [])],
            capture_output=True, text=True, env=self.env, cwd=self.sandbox, timeout=10,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_linux_activation_atomically_preserves_config_and_password_on_repeats(self):
        vault = self.activation_fixture()
        config = vault / "config.env"
        personal = ('# mes réglages\nPAGE_PASSWORD="secret-not-an-argument"\n'
                    'API_MODEL=mon-modele\nINBOX_TOKEN=mon-jeton\nCUSTOM="$(touch jamais)"\n')
        config.write_text(personal + 'PAGE_ORIGIN=https://ancienne.example.org\nPAGE_ORIGIN="https://doublon.example.org"')
        inode = config.stat().st_ino
        self.run_activation(vault)
        expected = personal + 'PAGE_ORIGIN="https://bobine.example.org"\n'
        self.assertEqual(config.read_text(), expected)
        self.assertNotEqual(config.stat().st_ino, inode, "replace must be atomic")
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
        self.assertFalse((self.sandbox / "jamais").exists())
        self.run_activation(vault)
        self.assertEqual(config.read_text(), expected)
        self.assertNotIn("secret-not-an-argument", self.calls.read_text())
        self.assertEqual(list(vault.glob(".config-page-*")), [])
        unit = self.home / ".config/systemd/user/bobine-page.service"
        command = next(line.split("=", 1)[1] for line in unit.read_text().splitlines() if line.startswith("ExecStart="))
        args = [arg.replace("%%", "%").replace("$$", "$") for arg in shlex.split(command)]
        self.assertEqual(args[1:], [str(vault / "page_server.py"), "--vault", str(vault)])
        self.assertNotIn("--local", command)
        self.assertNotIn("--password", command)
        self.assertNotIn("--port", command)
        self.assertNotIn("--bind", command)

    def test_linux_activation_creates_password_without_passing_it_to_a_command(self):
        vault = self.activation_fixture()
        self.run_activation(vault)
        text = (vault / "config.env").read_text()
        password = next(line.split("=", 1)[1].strip('"') for line in text.splitlines() if line.startswith("PAGE_PASSWORD="))
        self.assertEqual(len(password), 32)
        self.assertNotIn(password, self.calls.read_text())
        self.assertEqual(stat.S_IMODE((vault / "config.env").stat().st_mode), 0o600)

    def test_linux_activation_refuses_config_symlink_and_preserves_target(self):
        vault = self.activation_fixture()
        target = self.sandbox / "personal.env"
        target.write_text("personal\n")
        (vault / "config.env").symlink_to(target)
        before = snapshot(target)
        self.run_activation(vault, success=False)
        self.assertEqual(snapshot(target), before)
        self.assertTrue((vault / "config.env").is_symlink())
        self.assertNotIn("tunnel route", self.calls.read_text())
        self.assertNotIn("enable", self.calls.read_text())

    def test_linux_activation_refuses_foreign_service_without_writes(self):
        vault = self.activation_fixture()
        units = self.home / ".config/systemd/user"
        units.mkdir(parents=True)
        foreign = Path(str(vault) + "-autre")
        (units / "bobine-page.service").write_text(
            "[Service]\nExecStart=/usr/bin/python3 " + shlex.quote(str(foreign / "page_server.py")) +
            " --vault " + shlex.quote(str(foreign)) + "\n")
        before = snapshot(self.home)
        self.run_activation(vault, success=False)
        self.assertEqual(snapshot(self.home), before)
        self.assertFalse(self.calls.exists())

    def test_linux_activation_rejects_url_paths_options_and_missing_values(self):
        vault = self.activation_fixture()
        for host in ("https://bobine.example.org", "bobine.example.org/path", "bobine.example.org/",
                     "bobine.example.org:443", "user@bobine.example.org", "bobine.example.org\nBOGUS=yes"):
            with self.subTest(host=host):
                self.run_activation(vault, host, success=False)
                self.assertFalse((vault / "config.env").exists())
                self.assertFalse(self.calls.exists())
        for options in (["--vault"], ["--tunnel"], ["--unknown"], ["--tunnel", "../../autre"]):
            with self.subTest(options=options):
                self.run_activation(vault, success=False, options=options)
                self.assertFalse((vault / "config.env").exists())
                self.assertFalse(self.calls.exists())



    def test_mac_custom_vault_expands_safely_and_uses_code_paths(self):
        vault = self.page_fixture()
        data = self.home / 'Données & "vidéos"'
        data.mkdir()
        self.env["BOBINE_DATA"] = str(data)
        for setting in ('~/Données & "vidéos"', '$HOME/Données & "vidéos"',
                        '${HOME}/Données & "vidéos"', '${BOBINE_DATA}'):
            with self.subTest(setting=setting):
                # Single outer quotes preserve the double quotes in charger_config.
                (vault / "config.env").write_text(
                    "VAULT='" + setting + "'\nCARTE=non\nSYNC_ICLOUD=non\n"
                    f'NOTIF_CMD="$(touch {self.sandbox / "executed"})"\n')
                (data / "vault.html").write_text("obsolete page without chat\n")
                (data / "index.md").write_text("# Index\n")
                (data / "journal.json").write_text('{"personal": true}\n')
                before = (data / "index.md").read_bytes(), (data / "journal.json").read_bytes()
                self.run_page(vault)
                plist = self.home / "Library/LaunchAgents/com.bobine.page.plist"
                args = plistlib.loads(plist.read_bytes())["ProgramArguments"]
                self.assertEqual(args, [str(vault / ".venv/bin/python"), str(vault / "page_server.py"),
                                        "--vault", str(data), "--local"])
                self.assertIn("Demander", (data / "vault.html").read_text())
                self.assertIn("fixture only", (vault / "vault.html").read_text())
                self.assertEqual(before, ((data / "index.md").read_bytes(), (data / "journal.json").read_bytes()))
                self.assertFalse((self.sandbox / "executed").exists())
        shutil.copy2(ROOT / "desinstaller.sh", vault / "desinstaller.sh")
        (vault / "watch.sh").write_text("fixture\n")
        before = snapshot(vault), snapshot(data)
        self.run_bash([vault / "desinstaller.sh"])
        self.assertFalse(plist.exists())
        self.assertEqual((snapshot(vault), snapshot(data)), before)

    def test_mac_page_custom_vault_ownership_requires_both_code_and_data(self):
        vault = self.page_fixture()
        data = self.home / "data"
        data.mkdir()
        (vault / "config.env").write_text(f'VAULT="{data}"\n')
        shutil.copy2(ROOT / "desinstaller.sh", vault / "desinstaller.sh")
        (vault / "watch.sh").write_text("fixture\n")
        for code, effective in ((vault, vault), (Path(str(vault) + "-autre"), data)):
            with self.subTest(code=code, effective=effective):
                plist = self.page_plist(vault, target=code, effective=effective)
                before = snapshot(plist)
                self.run_page(vault)
                self.run_bash([vault / "desinstaller.sh"])
                self.assertEqual(snapshot(plist), before)
                self.assertFalse(self.calls.exists())
                self.assertEqual(self.shortcut_url(vault), (data / "vault.html").as_uri())

    def test_mac_page_refuses_unsafe_config_and_does_not_execute_vault_value(self):
        vault = self.page_fixture()
        plist = self.page_plist(vault)
        shutil.copy2(ROOT / "desinstaller.sh", vault / "desinstaller.sh")
        (vault / "watch.sh").write_text("fixture\n")
        config = vault / "config.env"
        for case in ("relative", "shell", "symlink", "directory"):
            with self.subTest(case=case):
                if config.is_symlink() or config.is_file():
                    config.unlink()
                if case == "relative":
                    config.write_text("VAULT=../other\n")
                elif case == "shell":
                    config.write_text(f'VAULT="$(touch {self.sandbox / "executed"})"\n')
                elif case == "symlink":
                    target = self.sandbox / "external-config"
                    target.write_text(f'VAULT="{vault}"\n')
                    config.symlink_to(target)
                else:
                    config.mkdir()
                before = snapshot(vault), snapshot(plist)
                original = config.read_text() if config.is_file() and not config.is_symlink() else None
                self.run_page(vault)
                self.run_bash([vault / "desinstaller.sh"])
                after = snapshot(vault), snapshot(plist)
                if original is None:
                    # Lien ou dossier : DEMANDER n'est même pas écrit.
                    self.assertEqual(after, before)
                else:
                    # Fichier ordinaire : seul le réglage DEMANDER s'ajoute (remplacement
                    # atomique, d'où la date du dossier) ; rien d'autre ne bouge.
                    ignore = (".", "config.env")
                    self.assertEqual({k: v for k, v in after[0].items() if k not in ignore},
                                     {k: v for k, v in before[0].items() if k not in ignore})
                    self.assertEqual(after[1], before[1])
                    self.assertTrue(config.read_text().startswith(original))
                    self.assertTrue(config.read_text().endswith("DEMANDER=oui\n"))
                self.assertFalse(self.calls.exists())
                self.assertFalse((self.sandbox / "executed").exists())

    def test_both_installers_regenerate_existing_page_after_dependencies_without_enrichment(self):
        for name in INSTALLERS:
            with self.subTest(installer=name):
                vault = self.home / ("generation-" + Path(name).stem)
                vault.mkdir()
                (vault / ".venv/bin").mkdir(parents=True)
                (vault / ".venv/bin/python").symlink_to(sys.executable)
                pip = vault / ".venv/bin/pip"
                pip.write_text('#!/bin/bash\nprintf "pip %s\\n" "$*" >> "$CALL_LOG"\n')
                pip.chmod(0o755)
                for module in ("ingest.py", "enrichir.py"):
                    shutil.copy2(ROOT / module, vault / module)
                # Executes the real generator; the wrapper checks dependency ordering.
                (vault / "generate_page.py").write_text(
                    'import os, runpy\nfrom pathlib import Path\n'
                    'assert "install -q -r requirements.txt" in Path(os.environ["CALL_LOG"]).read_text()\n'
                    'with open(os.environ["CALL_LOG"], "a") as f: f.write("generate\\n")\n'
                    # Any unexpected network attempt in generation fails this test.
                    'import socket\n'
                    'def forbidden(*a, **k): raise AssertionError("network forbidden")\n'
                    'socket.socket.connect = forbidden\n'
                    'socket.create_connection = forbidden\n'
                    f'runpy.run_path({str(ROOT / name).rsplit("/", 1)[0] + "/generate_page.py"!r}, run_name="__main__")\n')
                (vault / "config.env").write_text("CARTE=non\nSYNC_ICLOUD=non\n")
                (vault / "vault.html").write_text("old version without chat")
                (vault / "index.md").write_text("# Index\n")
                (vault / "journal.json").write_text('{"personal": true}\n')
                data_before = (vault / "index.md").read_bytes(), (vault / "journal.json").read_bytes()
                for command in ("ffmpeg", "sleep"):
                    (self.bin / command).write_text("#!/bin/bash\nexit 0\n")
                    (self.bin / command).chmod(0o755)
                text = (ROOT / name).read_text()
                helpers = text[text.index("if [ -t 1 ]; then"):text.index("# ------------------------------------------------------------------- bannière")]
                deps = text.split("# ---------------------------------------------------------------- 6. dépendances\n", 1)[1]
                # Les deux éditions génèrent la page juste après les dépendances
                # (bloc « génération locale »), avant toute question sur Demander.
                deps = deps.split("# ---------------------------------------------------------------- génération locale", 1)[0]
                code = ('set -u\nSCRIPT_DIR="$1"\nPY="$2"\ncd "$1" || exit 1\nDEPOT="$3"\n'
                        + helpers + deps + '\npreparer_page\n')
                self.run_bash(["-c", code, "generation", vault, sys.executable, (ROOT / name).parent])
                self.assertIn("Demander", (vault / "vault.html").read_text())
                self.assertEqual(data_before, ((vault / "index.md").read_bytes(), (vault / "journal.json").read_bytes()))
                self.assertEqual(self.calls.read_text().splitlines(), ["pip install --upgrade pip -q", "pip install -q -r requirements.txt", "generate"])
                self.calls.unlink()

    def test_linux_generation_uses_effective_data_vault(self):
        code = self.home / "linux-code"
        code.mkdir()
        data = self.home / 'Données & "vidéos"'
        data.mkdir()
        (code / ".venv/bin").mkdir(parents=True)
        (code / ".venv/bin/python").symlink_to(sys.executable)
        for module in ("generate_page.py", "enrichir.py", "ingest.py"):
            shutil.copy2(ROOT / "linux" / module, code / module)
        (code / "config.env").write_text("VAULT='${HOME}/Données & \"vidéos\"'\nCARTE=non\n")
        (code / "vault.html").write_text("keep code folder page\n")
        (data / "vault.html").write_text("old data page\n")
        text = (ROOT / "linux/install-linux.sh").read_text()
        helpers = text[text.index("if [ -t 1 ]; then"):text.index("# ------------------------------------------------------------------- bannière")]
        block = text.split("# ---------------------------------------------------------------- génération locale\n", 1)[1].split("# ---------------------------------------------------------------- 7.", 1)[0]
        self.run_bash(["-c", 'SCRIPT_DIR="$1"\nPY="$2"\nDEPOT="$3"\n' + helpers + block,
                       "generation", code, sys.executable, ROOT / "linux"])
        self.assertIn("Demander", (data / "vault.html").read_text())
        self.assertEqual((code / "vault.html").read_text(), "keep code folder page\n")
        self.assertFalse(self.calls.exists())

    def test_mac_default_code_directory_is_not_environment_expanded(self):
        vault = self.page_fixture()
        renamed = vault.with_name(vault.name + " $HOME")
        vault.rename(renamed)
        self.run_page(renamed)
        plist = self.home / "Library/LaunchAgents/com.bobine.page.plist"
        self.assertEqual(plistlib.loads(plist.read_bytes())["ProgramArguments"][3], str(renamed))
        self.assertIn("Demander", (renamed / "vault.html").read_text())

    def test_generation_failure_does_not_start_page_service(self):
        vault = self.page_fixture()
        (vault / "generate_page.py").write_text("raise SystemExit(1)\n")
        old = (vault / "vault.html").read_bytes()
        self.run_page(vault)
        self.assertEqual((vault / "vault.html").read_bytes(), old)
        self.assertEqual(self.shortcut_url(vault), (vault / "vault.html").as_uri())
        self.assertFalse(self.calls.exists())

    def test_linux_activation_then_uninstall_decodes_special_paths_and_retains_data(self):
        vault = self.activation_fixture()
        # Also verify single-pass decoding: literal %h / $$ must not expand again.
        renamed = vault.with_name(vault.name + r" \fin %h $$HOME")
        vault.rename(renamed)
        vault = renamed
        shutil.copy2(ROOT / "linux/desinstaller-linux.sh", vault / "desinstaller-linux.sh")
        (vault / "watch-linux.sh").write_text("fixture\n")
        (vault / "ingest.py").write_text("fixture\n")
        (vault / "vault.html").write_text("personal page\n")
        (vault / "Mon profil.txt").write_text("personal profile\n")
        (vault / ".bobine-jeton").write_text("personal token\n")
        (vault / "raw").mkdir()
        (vault / "raw/private.mp4").write_bytes(b"personal video")
        self.run_activation(vault)
        before = snapshot(vault)
        self.calls.unlink()
        self.run_bash([vault / "desinstaller-linux.sh"])
        self.assertEqual(snapshot(vault), before)
        self.assertEqual(list((self.home / ".config/systemd/user").iterdir()), [])
        self.assertIn("systemctl --user disable --now bobine-page.service bobine-tunnel.service\n", self.calls.read_text())
        self.assertNotIn("cloudflared", self.calls.read_text())

    def test_linux_uninstall_preserves_custom_or_unidentifiable_units(self):
        vault = self.activation_fixture()
        shutil.copy2(ROOT / "linux/desinstaller-linux.sh", vault / "desinstaller-linux.sh")
        (vault / "watch-linux.sh").write_text("fixture\n")
        (vault / "ingest.py").write_text("fixture\n")
        self.run_activation(vault)
        units = self.home / ".config/systemd/user"
        page = units / "bobine-page.service"
        original = page.read_text()
        cases = {
            "other-vault": original.replace("page_server.py", "page_server.py-other"),
            "other-data": original.replace('"--vault"', '"--unknown"'),
            "extra-args": original.replace("\nRestart=", " --bind 0.0.0.0\nRestart="),
            "ambiguous": original + "ExecStart=/bin/true\n",
            "undecodable": original.replace("$$argent", "$argent"),
            "literal-percent": original.replace("%%suite", "%suite"),
            "shell-wrapper": '[Service]\nExecStart=/bin/sh -c "echo ' + str(vault / "page_server.py") + '"\n',
        }
        self.calls.unlink()
        for case, text in cases.items():
            with self.subTest(case=case):
                page.write_text(text)
                before = snapshot(units)
                output = self.run_bash([vault / "desinstaller-linux.sh"])
                self.assertNotIn("Bobine est arrêté", output)
                self.assertIn("non reconnus", output)
                self.assertEqual(snapshot(units), before)
                self.assertFalse(self.calls.exists())
        page.write_text(original)
        for case in ("symlink", "dropin"):
            with self.subTest(case=case):
                if case == "symlink":
                    target = self.sandbox / "linked.service"
                    target.write_text(original)
                    page.unlink()
                    page.symlink_to(target)
                else:
                    page.unlink()
                    page.write_text(original)
                    dropin = units / "bobine-page.service.d"
                    dropin.mkdir()
                    (dropin / "custom.conf").write_text("[Service]\nExecStart=/bin/true\n")
                before = snapshot(units)
                output = self.run_bash([vault / "desinstaller-linux.sh"])
                self.assertNotIn("Bobine est arrêté", output)
                self.assertIn("non reconnus", output)
                self.assertEqual(snapshot(units), before)
                self.assertFalse(self.calls.exists())

    def test_linux_uninstall_recognizes_vault_reached_through_symlink(self):
        # L'activation enregistre le chemin réel (pwd -P) ; le désinstallateur,
        # lancé via un lien, voit le chemin affiché. Même dossier : reconnu.
        reel = self.activation_fixture()
        lien = self.home / "Bobine-lien"
        lien.symlink_to(reel, target_is_directory=True)
        shutil.copy2(ROOT / "linux/desinstaller-linux.sh", reel / "desinstaller-linux.sh")
        for nom in ("watch-linux.sh", "ingest.py"):
            (reel / nom).write_text("fixture\n")
        (reel / "config.env").write_text("")
        self.run_activation(lien)
        units = self.home / ".config/systemd/user"
        self.assertTrue((units / "bobine-page.service").exists())
        before = snapshot(reel)
        self.calls.unlink()
        self.run_bash([lien / "desinstaller-linux.sh"])
        self.assertEqual(snapshot(reel), before)
        self.assertIn("systemctl --user disable --now bobine-page.service bobine-tunnel.service\n",
                      self.calls.read_text())
        self.assertEqual(sorted(p.name for p in units.iterdir()), [])

    def test_linux_uninstall_symlink_still_refuses_other_vault(self):
        # Un lien vers un AUTRE dossier ne rend pas ses services reconnaissables.
        autre = self.activation_fixture()
        (autre / "config.env").write_text("")
        self.run_activation(autre)
        units = self.home / ".config/systemd/user"
        ici = self.home / "ici"
        ici.mkdir()
        for nom in ("watch-linux.sh", "ingest.py"):
            (ici / nom).write_text("fixture\n")
        shutil.copy2(ROOT / "linux/desinstaller-linux.sh", ici / "desinstaller-linux.sh")
        before = snapshot(units)
        self.calls.unlink()
        self.run_bash([ici / "desinstaller-linux.sh"])
        self.assertEqual(snapshot(units), before)
        self.assertFalse(self.calls.exists() and "disable" in self.calls.read_text())

    def test_linux_uninstall_keeps_unrelated_tunnel_even_if_page_is_owned(self):
        vault = self.activation_fixture()
        shutil.copy2(ROOT / "linux/desinstaller-linux.sh", vault / "desinstaller-linux.sh")
        (vault / "watch-linux.sh").write_text("fixture\n")
        (vault / "ingest.py").write_text("fixture\n")
        self.run_activation(vault)
        self.calls.unlink()
        tunnel = self.home / ".config/systemd/user/bobine-tunnel.service"
        tunnel.write_text(tunnel.read_text().replace("bobine-page.yml", "personal.yml"))
        before = snapshot(tunnel)
        self.run_bash([vault / "desinstaller-linux.sh"])
        self.assertEqual(snapshot(tunnel), before)
        self.assertNotIn("bobine-tunnel.service", self.calls.read_text())
        self.assertIn("disable --now bobine-page.service\n", self.calls.read_text())

    # ------------------------------------------------------------------
    # Demander activable : scripts, installateurs, réglage, raccourci.
    # ------------------------------------------------------------------

    EDITIONS = (ROOT, ROOT / "linux")

    def test_demander_scripts_exist_are_executable_and_parse(self):
        for edition in self.EDITIONS:
            for script in self.DEMANDER_SCRIPTS:
                with self.subTest(edition=edition.name, script=script):
                    path = edition / script
                    self.assertTrue(path.is_file())
                    if script != "page-locale.sh":  # chargé (source), jamais lancé
                        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
                    result = subprocess.run([shutil.which("bash"), "-n", str(path)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    # Ni tiret cadratin, ni jargon technique dans les messages affichés.
                    text = path.read_text(encoding="utf-8")
                    self.assertNotIn("\u2014", text)  # tiret cadratin
                    for line in text.splitlines():
                        if line.lstrip().startswith(("ok ", "note ", "avis ", "printf ")):
                            for jargon in ("LaunchAgent", "systemd", " port "):
                                self.assertNotIn(jargon, line)
        for script in ("install.sh", "desinstaller.sh", "linux/install-linux.sh",
                       "linux/desinstaller-linux.sh", "👉 2. Installer Bobine.command"):
            with self.subTest(script=script):
                result = subprocess.run([shutil.which("bash"), "-n", str(ROOT / script)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        # Les installateurs copient les scripts et les rendent exécutables.
        for installer in INSTALLERS:
            text = (ROOT / installer).read_text(encoding="utf-8")
            for script in self.DEMANDER_SCRIPTS:
                self.assertIn(script, text.split("for f in", 1)[1].split("done", 1)[0])

    def test_install_copies_demander_scripts_executable(self):
        for name in INSTALLERS:
            with self.subTest(script=name):
                depot = self.make_depot(name)
                for script in self.DEMANDER_SCRIPTS:
                    shutil.copy2((ROOT / name).parent / script, depot / script)
                for script in self.DEMANDER_SCRIPTS[1:]:
                    (depot / script).chmod(0o644)  # l'installateur rétablit 755
                target = self.home / ("demander-" + Path(name).stem)
                code = self.installer_harness(name)
                if name == "linux/install-linux.sh":
                    # Sous Linux, les droits sont rétablis dans « petits plus ».
                    text = (ROOT / name).read_text()
                    extra = text.split("# ------------------------------------------------- petits plus (dossier propre)\n", 1)[1]
                    code = code.replace('\nprintf "\\nTARGET=', '\n' + extra.split("# Une petite page", 1)[0] + 'printf "\\nTARGET=')
                self.run_bash(["-c", code, "installer-fixture", depot], f"{target}\n")
                for script in self.DEMANDER_SCRIPTS:
                    self.assertEqual((target / script).read_bytes(), (depot / script).read_bytes())
                for script in self.DEMANDER_SCRIPTS[1:]:
                    self.assertEqual(stat.S_IMODE((target / script).stat().st_mode), 0o755, script)

    # ------------------------------------------------------------ installateur Mac
    def mac_final_harness(self):
        text = (ROOT / "install.sh").read_text()
        helpers = text[text.index("if [ -t 1 ]; then"):
                       text.index("# ------------------------------------------------------------------- bannière")]
        block = text.split("# ---------------------------------------------------------------- 8. Demander\n", 1)[1]
        block = block.split("# ---------------------------------------------------------- générique de fin", 1)[0]
        return ('set -u\nSCRIPT_DIR="$1"\nPY="$2"\nDEPOT="$3"\ncd "$SCRIPT_DIR" || exit 1\n' + helpers +
                'NOM_VAULT=Bobine\nAPI_BLOC=""\nREVEIL=oui\nCARTE=non\nSYNC=non\nCRUSH_PRET=non\n'
                'GARDE=reinstall\nCIBLE="$SCRIPT_DIR"\n' + block)

    def run_mac_final(self, vault, answers):
        return self.run_bash(["-c", self.mac_final_harness(), "final", vault, sys.executable, ROOT], answers)

    def demander_lines(self, vault):
        return [line for line in (vault / "config.env").read_text().splitlines() if line.startswith("DEMANDER")]

    def test_mac_installer_last_question_yes_activates_and_summary_reflects_it(self):
        vault = self.page_fixture()
        output = self.run_mac_final(vault, "\n")  # défaut : O
        self.assertIn("Activer Demander (poser des questions à l'IA depuis ta page) ?", output)
        self.assertIn("[O/n]", output)
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=oui"])
        self.assertTrue((self.home / "Library/LaunchAgents/com.bobine.page.plist").exists())
        self.assertIn("Demander est activé. Ouvre « Ma page ».", output)
        self.assertIn("Pas encore de clé API", output)
        self.assertIn("Demander        : oui", output)
        self.assertIn("http://127.0.0.1:8786/, ce Mac uniquement", output)
        self.assertEqual(self.shortcut_url(vault), "http://127.0.0.1:8786/")
        for jargon in ("LaunchAgent", "launchd", "port "):
            self.assertNotIn(jargon, output)

    def test_mac_installer_no_then_activate_later(self):
        vault = self.page_fixture()
        output = self.run_mac_final(vault, "n\n")
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=non"])
        self.assertFalse((self.home / "Library/LaunchAgents/com.bobine.page.plist").exists())
        self.assertFalse(self.calls.exists(), "aucun service installé")
        self.assertIn("double-clique « Activer Demander »", output)
        self.assertIn("Demander        : non", output)
        self.assertIn("3. Ta page : double-clique « Ma page » (" + str(vault / "vault.html"), output)
        self.assertNotIn("8786", output)
        self.assertEqual(self.shortcut_url(vault), (vault / "vault.html").as_uri())
        # Défaut repris de l'ancien choix : Entrée garde « non ».
        output = self.run_mac_final(vault, "\n")
        self.assertIn("[o/N]", output)
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=non"])
        self.assertFalse(self.calls.exists())
        # Plus tard, sans réinstaller.
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=oui"])
        self.assertTrue((self.home / "Library/LaunchAgents/com.bobine.page.plist").exists())
        self.assertEqual(self.shortcut_url(vault), "http://127.0.0.1:8786/")

    def test_mac_installer_no_retires_own_previous_service(self):
        vault = self.page_fixture()
        self.run_any([vault / "activer-demander.sh"])
        self.run_mac_final(vault, "n\n")
        self.assertFalse((self.home / "Library/LaunchAgents/com.bobine.page.plist").exists())
        self.assertIn("bootout", self.calls.read_text())

    def test_mac_commands_created_once_and_never_overwritten(self):
        text = (ROOT / "install.sh").read_text()
        helpers = text[text.index("if [ -t 1 ]; then"):
                       text.index("# ------------------------------------------------------------------- bannière")]
        block = text.split("# ----------------------------------------------------- petits plus (macOS)\n", 1)[1]
        block = block.split("# Un petit README", 1)[0]
        code = 'set -u\ncd "$1" || exit 1\nDEPOT="$2"\n' + helpers + block
        folder = self.home / "commandes"
        folder.mkdir()
        self.run_bash(["-c", code, "petits-plus", folder, ROOT])
        for name, script in (("Activer Demander.command", "activer-demander.sh"),
                             ("Désactiver Demander.command", "desactiver-demander.sh")):
            path = folder / name
            self.assertEqual(path.read_text(), f'#!/bin/bash\ncd "$(dirname "$0")" || exit 1\nexec bash ./{script}\n')
            self.assertTrue(path.stat().st_mode & stat.S_IXUSR)
        # Personnalisé ou lien : jamais écrasé.
        (folder / "Activer Demander.command").write_text("#!/bin/bash\necho perso\n")
        (folder / "Désactiver Demander.command").unlink()
        target = self.sandbox / "perso.command"
        target.write_text("mon script\n")
        (folder / "Désactiver Demander.command").symlink_to(target)
        before = snapshot(folder), snapshot(target)
        self.run_bash(["-c", code, "petits-plus", folder, ROOT])
        self.assertEqual((snapshot(folder), snapshot(target)), before)

    # ------------------------------------------------------------ réglage DEMANDER
    def test_demander_setting_is_atomic_private_and_never_executed(self):
        for edition in self.EDITIONS:
            with self.subTest(edition=edition.name):
                folder = self.home / ("reglage-" + edition.name)
                folder.mkdir()
                for script in self.DEMANDER_SCRIPTS:
                    shutil.copy2(edition / script, folder / script)
                for module in ("enrichir.py",):
                    shutil.copy2(edition / module, folder / module)
                self.mac_stubs()
                sentinel = self.sandbox / ("execute-" + edition.name)
                config = folder / "config.env"
                head = ("# mes réglages\nNOM=\"Bobine\"\nDEMANDER=oui\n"
                        f'NOTIF_CMD="$(touch {sentinel})"\n# commentaire gardé\n')
                config.write_text(head + "  DEMANDER = peut-être\nAPI_MODEL=perso")
                config.chmod(0o644)
                inode = config.stat().st_ino
                code, output = self.run_any([folder / "desactiver-demander.sh"])
                self.assertEqual(code, 0, output)
                expected = head.replace("DEMANDER=oui", "DEMANDER=non") + "API_MODEL=perso\n"
                self.assertEqual(config.read_text(), expected)
                self.assertNotEqual(config.stat().st_ino, inode, "remplacement atomique")
                self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
                self.assertFalse(sentinel.exists())
                self.assertEqual(list(folder.glob(".config-demander-*")), [])
                # Idempotent : relancer ne réécrit pas un fichier déjà correct.
                inode = config.stat().st_ino
                self.run_any([folder / "desactiver-demander.sh"])
                self.assertEqual(config.read_text(), expected)
                self.assertEqual(config.stat().st_ino, inode)
                # Absent : ajouté à la fin, avec une ligne d'explication.
                config.write_text("NOM=Bobine\n")
                self.run_any([folder / "desactiver-demander.sh"])
                lines = config.read_text().splitlines()
                self.assertEqual(lines[0], "NOM=Bobine")
                self.assertEqual(lines[-1], "DEMANDER=non")
                self.assertTrue(lines[-2].startswith("# Demander"))
                self.assertNotIn("\u2014", config.read_text())

    def test_demander_refuses_linked_or_special_config_without_changes(self):
        for edition in self.EDITIONS:
            for script in ("activer-demander.sh", "desactiver-demander.sh"):
                for case in ("symlink", "directory"):
                    with self.subTest(edition=edition.name, script=script, case=case):
                        folder = self.home / f"lien-{edition.name}-{script}-{case}"
                        folder.mkdir()
                        for name in self.DEMANDER_SCRIPTS:
                            shutil.copy2(edition / name, folder / name)
                        shutil.copy2(edition / "enrichir.py", folder / "enrichir.py")
                        self.mac_stubs()
                        target = self.sandbox / f"perso-{edition.name}-{script}-{case}.env"
                        target.write_text("DEMANDER=oui\nPERSONNEL=1\n")
                        if case == "symlink":
                            (folder / "config.env").symlink_to(target)
                        else:
                            (folder / "config.env").mkdir()
                        before = snapshot(folder), snapshot(target)
                        code, output = self.run_any([folder / script])
                        self.assertNotEqual(code, 0)
                        self.assertIn("rien n'a été modifié", output)
                        self.assertEqual((snapshot(folder), snapshot(target)), before)
                        self.assertFalse(self.calls.exists())

    # ------------------------------------------------------------ Mac : cycle de vie
    def test_mac_disable_then_enable_keeps_data_and_is_idempotent(self):
        vault = self.page_fixture()
        for name in ("Mon profil.txt", "index.md", ".bobine-jeton"):
            (vault / name).write_text("personnel\n")
        (vault / "raw").mkdir()
        (vault / "raw/video.mp4").write_bytes(b"video")
        plist = self.home / "Library/LaunchAgents/com.bobine.page.plist"
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertEqual(code, 0, output)
        first = plist.read_bytes()
        config_first = (vault / "config.env").read_bytes()
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertEqual(plist.read_bytes(), first)
        self.assertEqual((vault / "config.env").read_bytes(), config_first)
        data = {name: snapshot(vault / name) for name in ("Mon profil.txt", "index.md", ".bobine-jeton", "raw")}
        self.calls.unlink()
        code, output = self.run_any([vault / "desactiver-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertIn("Demander est désactivé", output)
        self.assertIn("Aucune donnée n'a été supprimée", output)
        self.assertFalse(plist.exists())
        self.assertIn("launchctl bootout gui/", self.calls.read_text())
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=non"])
        self.assertEqual(self.shortcut_url(vault), (vault / "vault.html").as_uri())
        self.calls.unlink()
        code, output = self.run_any([vault / "desactiver-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertFalse(self.calls.exists(), "désactiver deux fois ne touche à rien")
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertEqual(plist.read_bytes(), first)
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=oui"])
        self.assertEqual({name: snapshot(vault / name) for name in data}, data)

    def test_mac_disable_never_removes_foreign_service(self):
        vault = self.page_fixture()
        for case in ("other-vault", "symlink", "malformed"):
            with self.subTest(case=case):
                plist = self.page_plist(vault, Path(str(vault) + "-autre"))
                if case == "symlink":
                    target = self.sandbox / "perso.plist"
                    target.write_bytes(plist.read_bytes().replace(b"-autre", b""))
                    plist.unlink()
                    plist.symlink_to(target)
                elif case == "malformed":
                    plist.write_text("<plist>")
                before = snapshot(plist.parent), snapshot(vault / "vault.html")
                code, output = self.run_any([vault / "desactiver-demander.sh"])
                self.assertEqual(code, 0, output)
                self.assertIn("elle est conservée", output)
                self.assertEqual((snapshot(plist.parent), snapshot(vault / "vault.html")), before)
                self.assertFalse(self.calls.exists())
                plist.unlink()

    def test_mac_port_busy_or_foreign_service_is_kept_by_activation(self):
        vault = self.page_fixture()
        self.env["PORT_OCCUPE"] = "1"
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertNotEqual(code, 0)
        self.assertIn("Une autre application utilise déjà l'adresse de ta page", output)
        self.assertNotIn("bootstrap", self.calls.read_text() if self.calls.exists() else "")
        self.assertFalse((self.home / "Library/LaunchAgents/com.bobine.page.plist").exists())
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=oui"])

    def test_mac_uninstall_after_activation_is_symmetric(self):
        vault = self.page_fixture()
        self.osacompile_stub()
        shutil.copy2(ROOT / "desinstaller.sh", vault / "desinstaller.sh")
        (vault / "watch.sh").write_text("fixture\n")
        self.run_any([vault / "activer-demander.sh"])
        plist = self.home / "Library/LaunchAgents/com.bobine.page.plist"
        self.assertTrue(plist.exists())
        before = snapshot(vault)
        self.run_bash([vault / "desinstaller.sh"])
        self.assertFalse(plist.exists())
        self.assertEqual(snapshot(vault), before, "raccourci, réglage et données conservés")

    # ------------------------------------------------------------ Mac : « Ma page »
    def test_mac_app_shortcut_is_relocatable_marked_and_migrates_our_webloc(self):
        vault = self.page_fixture()
        self.osacompile_stub()
        webloc = vault / "Ma page.webloc"
        webloc.write_bytes(plistlib.dumps({"URL": (vault / "vault.html").as_uri()}))
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertEqual(code, 0, output)
        app = vault / "Ma page.app"
        self.assertEqual((app / "Contents/Resources/bobine-ma-page.txt").read_text(),
                         "Bobine : raccourci Ma page (version 1)\n")
        source = (app / "Contents/Resources/Scripts/main.scpt").read_text()
        self.assertIn("path to me", source)
        self.assertIn('"/usr/bin/dirname "', source)
        self.assertIn('"/bin/bash " & quoted form of (dossier & "/ouvrir-ma-page.sh")', source)
        self.assertNotIn(str(vault), source, "l'application calcule son dossier : relocalisable")
        self.assertFalse(webloc.exists(), "notre ancien raccourci est remplacé")
        self.assertEqual(list(vault.glob(".ma-page-*")), [])
        before = snapshot(app)
        self.run_any([vault / "desactiver-demander.sh"])
        self.run_any([vault / "activer-demander.sh"])
        self.assertEqual(snapshot(app), before, "jamais recréée")
        self.assertFalse(webloc.exists())

    def test_mac_app_keeps_personal_webloc_and_foreign_app(self):
        vault = self.page_fixture()
        self.osacompile_stub()
        webloc = vault / "Ma page.webloc"
        webloc.write_bytes(plistlib.dumps({"URL": "https://perso.example.org/"}))
        before = snapshot(webloc)
        self.run_any([vault / "activer-demander.sh"])
        self.assertTrue((vault / "Ma page.app/Contents/Resources/bobine-ma-page.txt").exists())
        self.assertEqual(snapshot(webloc), before)
        # Une application « Ma page.app » sans notre marqueur n'est jamais touchée ;
        # le raccourci de secours .webloc prend le relais.
        shutil.rmtree(vault / "Ma page.app")
        webloc.unlink()
        foreign = vault / "Ma page.app"
        (foreign / "Contents/Resources").mkdir(parents=True)
        (foreign / "Contents/Resources/bobine-ma-page.txt").write_text("autre chose\n")
        before = snapshot(foreign)
        output = self.run_any([vault / "activer-demander.sh"])[1]
        self.assertIn("Ton « Ma page » personnel est conservé.", output)
        self.assertEqual(snapshot(foreign), before)
        self.assertEqual(self.shortcut_url(vault), "http://127.0.0.1:8786/")

    def test_mac_shortcut_falls_back_to_webloc_without_osacompile(self):
        for case in ("absent", "failing"):
            with self.subTest(case=case):
                vault = self.page_fixture()
                if case == "absent":
                    (self.bin / "osacompile").unlink()
                self.run_any([vault / "activer-demander.sh"])
                self.assertFalse((vault / "Ma page.app").exists())
                self.assertEqual(self.shortcut_url(vault), "http://127.0.0.1:8786/")
                self.run_any([vault / "desactiver-demander.sh"])
                self.assertEqual(self.shortcut_url(vault), (vault / "vault.html").as_uri())
                self.assertEqual(list(vault.glob(".ma-page-*")), [])
                shutil.rmtree(vault)

    # ------------------------------------------------------------ Mac : ouvrir-ma-page.sh
    def opened_lines(self):
        return self.opened.read_text().splitlines() if self.opened.exists() else []

    def test_mac_open_page_uses_local_address_when_healthy_or_restartable(self):
        vault = self.page_fixture()
        self.run_any([vault / "activer-demander.sh"])
        cases = {
            "healthy": lambda: None,
            "unloaded": lambda: (self.home / "page-loaded").unlink(),
            "stopped": lambda: (self.home / "page-stopped").write_text(""),
        }
        for case, prepare in cases.items():
            with self.subTest(case=case):
                prepare()
                if self.calls.exists():
                    self.calls.unlink()
                if self.opened.exists():
                    self.opened.unlink()
                code, output = self.run_any([vault / "ouvrir-ma-page.sh"])
                self.assertEqual(code, 0, output)
                self.assertEqual(self.opened_lines(), ["http://127.0.0.1:8786/"])
                calls = self.calls.read_text() if self.calls.exists() else ""
                if case == "unloaded":
                    self.assertIn("launchctl bootstrap gui/", calls)
                elif case == "stopped":
                    self.assertIn("launchctl kickstart gui/", calls)
                else:
                    self.assertEqual(calls, "")

    def test_mac_open_page_falls_back_to_file(self):
        vault = self.page_fixture()
        page = str(vault / "vault.html")
        self.run_any([vault / "activer-demander.sh"])
        # Échec de redémarrage : la page fichier s'ouvre, sans erreur.
        (self.home / "page-stopped").write_text("")
        self.env["KICKSTART_FAIL"] = "1"
        code, output = self.run_any([vault / "ouvrir-ma-page.sh"])
        self.assertEqual(code, 0, output)
        self.assertEqual(self.opened_lines(), [page])
        del self.env["KICKSTART_FAIL"]
        # Désactivé : jamais l'adresse locale, aucun service lancé.
        self.run_any([vault / "desactiver-demander.sh"])
        self.opened.unlink()
        self.calls.unlink()
        self.assertEqual(self.run_any([vault / "ouvrir-ma-page.sh"])[0], 0)
        self.assertEqual(self.opened_lines(), [page])
        self.assertFalse(self.calls.exists())
        # Activé dans config.env mais service d'un autre dossier : page fichier.
        (vault / "config.env").write_text("DEMANDER=oui\n")
        self.page_plist(vault, Path(str(vault) + "-autre"))
        self.opened.unlink()
        self.assertEqual(self.run_any([vault / "ouvrir-ma-page.sh"])[0], 0)
        self.assertEqual(self.opened_lines(), [page])
        self.assertFalse(self.calls.exists())
        # Sans le fichier partagé : la page fichier quand même.
        (vault / "page-locale.sh").unlink()
        self.opened.unlink()
        self.assertEqual(self.run_any([vault / "ouvrir-ma-page.sh"])[0], 0)
        self.assertEqual(self.opened_lines(), [page])

    # ------------------------------------------------------------ Linux
    def linux_fixture(self):
        vault = self.home / 'Linux Demander & "citation" $argent %suite'
        vault.mkdir()
        (vault / ".venv/bin").mkdir(parents=True)
        # Jamais lancé comme service : systemctl et la sonde HTTP sont simulés.
        (vault / ".venv/bin/python").symlink_to(sys.executable)
        (vault / "page_server.py").write_text("fixture only\n")
        for module in ("generate_page.py", "enrichir.py", "ingest.py"):
            shutil.copy2(ROOT / "linux" / module, vault / module)
        for script in self.DEMANDER_SCRIPTS + ("desinstaller-linux.sh",):
            shutil.copy2(ROOT / "linux" / script, vault / script)
        (vault / "watch-linux.sh").write_text("fixture\n")
        (vault / "config.env").write_text(f'X="$(touch {self.sandbox / "executed"})"\nCARTE=non\n')
        self.linux_stubs()
        for variable in ("DISPLAY", "WAYLAND_DISPLAY"):
            self.env.pop(variable, None)
        return vault

    def linux_stubs(self):
        self.opened = self.sandbox / "opened"
        self.env["OPEN_LOG"] = str(self.opened)
        self.stub("sleep", "#!/bin/bash\nexit 0\n")
        self.stub("systemctl",
                  '#!/bin/bash\nprintf "systemctl %s\\n" "$*" >> "$CALL_LOG"\n'
                  '[ "${SYSTEMD_ABSENT:-0}" = 1 ] && exit 1\n'
                  'case "$*" in\n'
                  '  *is-active*) [ -e "$HOME/page-active" ]; exit $? ;;\n'
                  '  *"show -p LoadState"*) [ "${UNITE_AILLEURS:-0}" = 1 ] && echo loaded; exit 0 ;;\n'
                  '  *"disable --now"*|*" stop "*) rm -f "$HOME/page-active" ;;\n'
                  '  *"enable --now"*|*restart*|*" start "*) [ "${START_FAIL:-0}" = 1 ] || touch "$HOME/page-active" ;;\n'
                  'esac\nexit 0\n')
        self.stub("curl",
                  '#!/bin/bash\n'
                  'if [ -e "$HOME/page-active" ]; then printf "ok\\n\\n200"; exit 0; fi\n'
                  'if [ "${PORT_OCCUPE:-0}" = 1 ]; then printf "autre\\n404"; exit 0; fi\n'
                  'exit 7\n')
        self.stub("xdg-open", '#!/bin/bash\nprintf "%s\\n" "$*" >> "$OPEN_LOG"\n')

    def unit_path(self):
        return self.home / ".config/systemd/user/bobine-page.service"

    def unit_args(self):
        command = next(line.split("=", 1)[1] for line in self.unit_path().read_text().splitlines()
                       if line.startswith("ExecStart="))
        return [arg.replace("%%", "%").replace("$$", "$") for arg in shlex.split(command)]

    def test_linux_activation_installs_marked_local_page_with_password(self):
        vault = self.linux_fixture()
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertEqual(code, 0, output)
        unit = self.unit_path().read_text()
        self.assertIn("\n# Créé par activer-demander.sh\n", unit)
        self.assertEqual(self.unit_args(), [str(vault / ".venv/bin/python"), str(vault / "page_server.py"),
                                            "--vault", str(vault)])
        for option in ("--password", "--bind", "--port", "--local"):
            self.assertNotIn(option, unit)
        config = (vault / "config.env").read_text()
        password = next(line.split("=", 1)[1].strip('"') for line in config.splitlines()
                        if line.startswith("PAGE_PASSWORD="))
        self.assertEqual(len(password), 32)
        self.assertNotIn(password, self.calls.read_text())
        self.assertNotIn(password, output)
        self.assertEqual(stat.S_IMODE((vault / "config.env").stat().st_mode), 0o600)
        self.assertIn("systemctl --user enable --now bobine-page.service", self.calls.read_text())
        self.assertIn("ssh -L 8786:127.0.0.1:8786", output)
        self.assertIn("ligne PAGE_PASSWORD", output)
        self.assertIn("Pas encore de clé API", output)
        self.assertFalse((self.sandbox / "executed").exists())
        for jargon in ("systemd", "LaunchAgent"):
            self.assertNotIn(jargon, output)
        # Idempotent : relancer redémarre la même page, sans nouveau mot de passe.
        before = self.unit_path().read_bytes(), (vault / "config.env").read_bytes()
        self.calls.unlink()
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertEqual((self.unit_path().read_bytes(), (vault / "config.env").read_bytes()), before)
        self.assertIn("systemctl --user restart bobine-page.service", self.calls.read_text())
        # Reconnue (et retirée) par le désinstallateur, données conservées.
        data = snapshot(vault)
        self.calls.unlink()
        self.run_bash([vault / "desinstaller-linux.sh"])
        self.assertFalse(self.unit_path().exists())
        self.assertIn("systemctl --user disable --now bobine-page.service\n", self.calls.read_text())
        self.assertEqual(snapshot(vault), data)

    def test_linux_activation_keeps_foreign_or_busy_and_handles_missing_systemd(self):
        vault = self.linux_fixture()
        units = self.unit_path().parent
        units.mkdir(parents=True)
        foreign = Path(str(vault) + "-autre")
        self.unit_path().write_text("[Service]\nExecStart=/usr/bin/python3 " + shlex.quote(str(foreign / "page_server.py"))
                                    + " --vault " + shlex.quote(str(foreign)) + "\n")
        before = snapshot(units)
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertNotEqual(code, 0)
        self.assertIn("elle est conservée", output)
        self.assertEqual(snapshot(units), before)
        self.assertNotIn("restart", self.calls.read_text())
        self.assertNotIn("enable", self.calls.read_text())
        self.unit_path().unlink()
        for variable, message in (("PORT_OCCUPE", "Une autre application utilise déjà"),
                                  ("UNITE_AILLEURS", "déjà installée ailleurs"),
                                  ("SYSTEMD_ABSENT", "ne permet pas de lancer ta page en arrière-plan")):
            with self.subTest(case=variable):
                self.env[variable] = "1"
                self.calls.unlink()
                code, output = self.run_any([vault / "activer-demander.sh"])
                self.assertNotEqual(code, 0)
                self.assertIn(message, output)
                self.assertFalse(self.unit_path().exists())
                self.assertNotIn("enable", self.calls.read_text())
                self.assertEqual(self.demander_lines(vault), ["DEMANDER=oui"])
                del self.env[variable]
        # Démarrage raté : l'unité créée n'est pas laissée en boucle.
        self.env["START_FAIL"] = "1"
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertNotEqual(code, 0)
        self.assertIn("Ta page n'a pas démarré", output)
        self.assertFalse(self.unit_path().exists())
        self.assertIn("disable --now bobine-page.service", self.calls.read_text())

    def test_linux_disable_removes_marked_unit_without_tunnel(self):
        vault = self.linux_fixture()
        self.run_any([vault / "activer-demander.sh"])
        data = {name: snapshot(vault / name) for name in ("vault.html", "page_server.py", ".venv")}
        self.calls.unlink()
        code, output = self.run_any([vault / "desactiver-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertFalse(self.unit_path().exists())
        self.assertIn("systemctl --user disable --now bobine-page.service", self.calls.read_text())
        self.assertIn("Aucune donnée n'a été supprimée", output)
        self.assertIn(str(vault / "vault.html"), output)
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=non"])
        self.assertTrue(any(line.startswith("PAGE_PASSWORD=") for line in (vault / "config.env").read_text().splitlines()))
        self.assertEqual({name: snapshot(vault / name) for name in data}, data)
        # Réactivation : la page locale revient.
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertTrue(self.unit_path().exists())

    def test_linux_disable_with_public_tunnel_restarts_and_keeps_units(self):
        vault = self.activation_fixture()
        self.run_activation(vault)  # page web publique (activer-page-web.sh)
        for script in self.DEMANDER_SCRIPTS:
            shutil.copy2(ROOT / "linux" / script, vault / script)
        shutil.copy2(ROOT / "linux/enrichir.py", vault / "enrichir.py")
        self.linux_stubs()
        units = self.unit_path().parent
        before = snapshot(units)
        self.calls.unlink()
        code, output = self.run_any([vault / "desactiver-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertIn("systemctl --user restart bobine-page.service", self.calls.read_text())
        self.assertNotIn("disable", self.calls.read_text())
        self.assertEqual(snapshot(units), before)
        self.assertIn("reste en ligne", output)
        # Réactivation : même page publique, redémarrée, adresse publique affichée.
        self.calls.unlink()
        code, output = self.run_any([vault / "activer-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertIn("systemctl --user restart bobine-page.service", self.calls.read_text())
        self.assertEqual(snapshot(units), before)
        self.assertIn("Ta page : https://bobine.example.org", output)
        self.assertNotIn("ssh -L", output)

    def test_linux_disable_never_touches_foreign_unit(self):
        vault = self.linux_fixture()
        self.run_any([vault / "activer-demander.sh"])
        unit = self.unit_path()
        unit.write_text(unit.read_text().replace("page_server.py", "page_server.py-autre"))
        before = snapshot(unit.parent)
        self.calls.unlink()
        code, output = self.run_any([vault / "desactiver-demander.sh"])
        self.assertEqual(code, 0, output)
        self.assertIn("elle est conservée", output)
        self.assertEqual(snapshot(unit.parent), before)
        self.assertFalse(self.calls.exists())

    def test_linux_open_page_starts_and_shows_address_or_file(self):
        vault = self.linux_fixture()
        self.run_any([vault / "activer-demander.sh"])
        (self.home / "page-active").unlink()  # arrêtée
        self.calls.unlink()
        code, output = self.run_any([vault / "ouvrir-ma-page.sh"])
        self.assertEqual(code, 0, output)
        self.assertIn("systemctl --user start bobine-page.service", self.calls.read_text())
        self.assertIn("ssh -L 8786:127.0.0.1:8786", output)
        self.assertFalse(self.opened.exists(), "pas d'écran : pas de navigateur")
        self.env["DISPLAY"] = ":0"
        self.run_any([vault / "ouvrir-ma-page.sh"])
        self.assertEqual(self.opened_lines(), ["http://127.0.0.1:8786/"])
        with open(vault / "config.env", "a") as config:
            config.write('PAGE_ORIGIN="https://bobine.example.org"\n')
        output = self.run_any([vault / "ouvrir-ma-page.sh"])[1]
        self.assertIn("Ta page : https://bobine.example.org", output)
        # Désactivé : chemin de vault.html et astuce de copie, aucun service lancé.
        self.run_any([vault / "desactiver-demander.sh"])
        self.opened.unlink()
        self.calls.unlink()
        code, output = self.run_any([vault / "ouvrir-ma-page.sh"])
        self.assertEqual(code, 0, output)
        self.assertIn(str(vault / "vault.html"), output)
        self.assertIn("scp ", output)
        self.assertEqual(self.opened_lines(), [str(vault / "vault.html")])
        self.assertFalse(self.calls.exists())

    def linux_final_harness(self):
        text = (ROOT / "linux/install-linux.sh").read_text()
        helpers = text[text.index("if [ -t 1 ]; then"):
                       text.index("# ------------------------------------------------------------------- bannière")]
        block = text.split("# ---------------------------------------------------------------- 8. Demander\n", 1)[1]
        block = block.split("# ---------------------------------------------------------- générique de fin", 1)[0]
        return ('set -u\nSCRIPT_DIR="$1"\nPY="$2"\nDEPOT="$3"\ncd "$SCRIPT_DIR" || exit 1\n' + helpers +
                'NOM_VAULT=Bobine\nAPI_BLOC=""\nREVEIL=oui\nCARTE=non\nGARDE=reinstall\nCIBLE="$SCRIPT_DIR"\n' + block)

    def test_linux_installer_last_question_yes_or_no(self):
        vault = self.linux_fixture()
        harness = self.linux_final_harness()
        output = self.run_bash(["-c", harness, "final", vault, sys.executable, ROOT / "linux"], "n\n")
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=non"])
        self.assertFalse(self.unit_path().exists())
        self.assertNotIn("enable", self.calls.read_text() if self.calls.exists() else "")
        self.assertIn("./activer-demander.sh", output)
        self.assertIn("Demander        : non", output)
        self.assertIn("4. Ta page : " + str(vault / "vault.html"), output)
        output = self.run_bash(["-c", harness, "final", vault, sys.executable, ROOT / "linux"], "\n")
        self.assertIn("[o/N]", output)
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=non"])
        output = self.run_bash(["-c", harness, "final", vault, sys.executable, ROOT / "linux"], "o\n")
        self.assertEqual(self.demander_lines(vault), ["DEMANDER=oui"])
        self.assertIn("# Créé par activer-demander.sh", self.unit_path().read_text())
        self.assertIn("Demander        : oui", output)
        self.assertIn("./ouvrir-ma-page.sh", output)
        self.assertIn("Page régénérée localement", output)


if __name__ == "__main__":
    unittest.main()
