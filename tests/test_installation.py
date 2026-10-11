#!/usr/bin/env python3
"""Installation safety regressions, using only stdlib, bash and temporary homes.

Run: python3 -m unittest discover -s tests -p test_installation.py -v
Uninstallers run in full. Installer selection/copy and config sections run in
isolation, so dependency installation and real background services never run.
"""

import os
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
        self.sandbox = Path(temporary.name)
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
            "config.env": 'NOM="Bobine"\n',
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
            files = {
                "bobine-watch.service": f"ExecStart=/bin/bash {target}/watch-linux.sh\n",
                "bobine-watch.timer": "Timer\n",
                "bobine-watch.path": "Path\n",
                "bobine-inbox.service": f"ExecStart=/usr/bin/python3 {target}/inbox_server.py --vault {target}\n",
                "bobine-page.service": f"ExecStart=/usr/bin/python3 {target}/page_server.py --vault {target}\n",
                "bobine-tunnel.service": "Tunnel\n",
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


if __name__ == "__main__":
    unittest.main()
