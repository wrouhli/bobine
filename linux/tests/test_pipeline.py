"""Régressions du parcours quotidien : vidéos visibles, pause et reprise sûres."""
import contextlib
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import enrichir  # noqa: E402
import ingest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class VideosToujoursVisibles(unittest.TestCase):
    def vault(self, dossier, config):
        root = Path(dossier)
        (root / 'raw').mkdir()
        (root / 'config.env').write_text('CARTE=non\nSYNC_ICLOUD=non\n' + config)
        for n in range(6):
            (root / 'raw' / f'insta_{n}.md').write_text(
                f'---\nsource: https://www.instagram.com/reel/V{n}/\nauteur: a\n---\n# Vidéo {n}\n')
        return root

    def run_resume(self, root, response, extra=()):
        with mock.patch.object(sys, 'argv', ['enrichir.py', '--vault', str(root), *extra]), \
                mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(enrichir, 'demander_resume', return_value=response) as request, \
                contextlib.redirect_stdout(io.StringIO()):
            code = enrichir.main()
        return code, request.call_count

    def assert_visible(self, root):
        index = (root / 'index.md').read_text()
        html = (root / 'vault.html').read_text()
        self.assertEqual(index.count('\n### '), 6)
        self.assertEqual(html.count('class="carte"'), 6)
        for n in range(6):
            self.assertIn(f'Vidéo {n}', html)

    def test_panne_et_limite_ne_cachent_aucune_video(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.vault(d, 'DEEPSEEK_API_KEY=fixture-only\n')
            code, calls = self.run_resume(root, None)
            self.assertEqual(code, enrichir.CODE_ECHEC_API)
            self.assertEqual(calls, enrichir.ECHECS_AVANT_PAUSE)
            self.assert_visible(root)
            self.run_resume(root, None, ['--limite', '1'])
            self.assert_visible(root)

    def test_sans_modele_toutes_les_videos_restent_visibles(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.vault(d, 'OPENAI_API_KEY=fixture-only\n')
            code, calls = self.run_resume(root, None)
            self.assertEqual(code, enrichir.CODE_ECHEC_API)
            self.assertEqual(calls, 0)
            self.assert_visible(root)

    def test_sans_cle_limite_ne_cache_pas_les_videos(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.vault(d, '')
            code, calls = self.run_resume(root, None, ['--limite', '1'])
            self.assertEqual(code, 0)
            self.assertEqual(calls, 0)
            self.assert_visible(root)

    def test_reponse_vide_reste_en_attente(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.vault(d, 'DEEPSEEK_API_KEY=fixture-only\n')
            code, _ = self.run_resume(root, {})
            self.assertEqual(code, enrichir.CODE_ECHEC_API)
            self.assertIn(enrichir.MARQUEUR_ATTENTE, (root / 'index.md').read_text())
            self.assert_visible(root)

    def test_generation_ratee_est_retentee_sans_nouvelle_video(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.vault(d, "DEEPSEEK_API_KEY=fixture-only\n")
            with mock.patch.object(enrichir, "regenerer_pages") as pages:
                self.run_resume(root, None)
                self.assertEqual(pages.call_count, 1)
            # Retour du générateur, mais le service de résumé reste indisponible.
            self.run_resume(root, None)
            self.assert_visible(root)

    def test_connexion_coupee_est_un_echec_gere(self):
        with mock.patch.object(enrichir.urllib.request, 'urlopen',
                               side_effect=http.client.RemoteDisconnected('fixture')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(enrichir.demander_resume('fixture-only',
                                                          'https://example.invalid', 'model', 'text'))


class CompteurReel(unittest.TestCase):
    def test_chaque_echec_compte_et_rollover(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for _ in range(3):
                ingest.enregistrer_essai(root, '2026-10-11')
            self.assertEqual(ingest.compter_essais(root, '2026-10-11'), 3)
            self.assertEqual(ingest.compter_essais(root, '2026-10-12'), 0)
            ingest.enregistrer_essai(root, '2026-10-12')
            self.assertEqual(ingest.compter_essais(root, '2026-10-12'), 1)

    def test_compteur_abime_ne_permet_pas_de_telecharger(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / '.ingest-essais.json').write_text('broken')
            with self.assertRaises(ValueError):
                ingest.enregistrer_essai(root)

    def test_migration_compte_prudemment_anciens_essais(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'raw').mkdir()
            (root / 'raw/a.md').write_text('---\ntraite_le: 2026-10-11\n---\n')
            (root / 'journal.json').write_text(json.dumps({'u': {
                'statut': 'echec', 'essai_le': '2026-10-11', 'tentatives': 2}}))
            self.assertEqual(ingest.compter_essais(root, '2026-10-11'), 3)

    def test_plafond50_inclut_les_reessais(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inbox = root / 'liens.txt'
            inbox.write_text('\n'.join(f'https://www.instagram.com/reel/V{i}/' for i in range(100)))
            calls = []

            def fail(url, cookies):
                calls.append(url)
                raise RuntimeError('fixture inaccessible')

            with mock.patch.object(ingest, 'verifier_outils'), \
                    mock.patch.object(ingest, 'recuperer_metadonnees', side_effect=fail), \
                    mock.patch.object(ingest, 'recuperer_carrousel', return_value=''), \
                    mock.patch.object(ingest.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
                for _ in range(8):
                    with mock.patch.object(sys, 'argv', ['ingest.py', str(inbox), '--vault', str(root),
                                                        '--limite', '15', '--plafond-journalier', '50']):
                        ingest.main()
            self.assertEqual(len(calls), 50)
            self.assertEqual(ingest.compter_essais(root), 50)


@unittest.skipIf(shutil.which('bash') is None, 'bash requis')
class RelanceResume(unittest.TestCase):
    def test_plafond_n_empeche_pas_les_resumes(self):
        scripts = [p for p in (ROOT / 'watch.sh', ROOT / 'linux/watch-linux.sh',
                               ROOT / 'watch-linux.sh') if p.is_file()]
        self.assertTrue(scripts)
        for script in scripts:
            with self.subTest(script=script.name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                home = root / 'home'
                home.mkdir()
                vault = root / 'vault'
                vault.mkdir()
                shutil.copy(script, vault / script.name)
                (vault / '.venv/bin').mkdir(parents=True)
                python = vault / '.venv/bin/python'
                python.write_text('#!/bin/bash\n'
                                  'case "$*" in\n'
                                  '*--compter-essais*) echo 50 ;;\n'
                                  '*enrichir.py*) echo resumed >> "$(dirname "$0")/../../resumed" ;;\n'
                                  '*) echo unexpected >> "$(dirname "$0")/../../ingested" ;;\n'
                                  'esac\n')
                python.chmod(0o755)
                env = os.environ.copy()
                env['HOME'] = str(home)
                result = subprocess.run(['bash', str(vault / script.name)], env=env,
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((vault / 'resumed').exists())
                self.assertFalse((vault / 'ingested').exists())
