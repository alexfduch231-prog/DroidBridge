"""WOL diagnostics are local, bounded, read-only and never a wake guarantee."""
import json
import queue
import subprocess
import unittest
from unittest.mock import patch

try:
    from desktop import wol_setup as wol
except ImportError:
    wol = None


class WolSetupTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(wol, 'WOL setup module must exist')
        if hasattr(wol, '_setup_uncertain'):
            wol._setup_uncertain.clear()
            self.addCleanup(wol._setup_uncertain.clear)

    def payload(self, **changes):
        data = {'adapter': {'name': 'Ethernet', 'guid': '{00000000-0000-0000-0000-000000000001}',
                            'status': 'Up', 'magic_packet': 'Enabled'}, 'selection': 'default_route'}
        data.update(changes)
        return json.dumps(data)

    def test_enabled_is_only_windows_setting_not_wake_success(self):
        report = wol.parse_diagnostics(self.payload())
        self.assertEqual(report.magic_packet, 'enabled')
        self.assertIn('Windows', wol.summary_text(report))
        self.assertIn('не проверено', wol.summary_text(report))
        self.assertFalse(report.wake_verified)

    def test_disabled_unsupported_missing_and_unknown_are_distinct(self):
        for raw, expected in [('Disabled', 'disabled'), ('Unsupported', 'unsupported'),
                              (None, 'unknown'), ('driver surprise', 'unknown')]:
            data = json.loads(self.payload())
            data['adapter']['magic_packet'] = raw
            with self.subTest(raw=raw):
                self.assertEqual(wol.parse_diagnostics(json.dumps(data)).magic_packet, expected)

    def test_no_active_physical_default_route_does_not_claim_support(self):
        report = wol.parse_diagnostics(self.payload(adapter=None))
        self.assertEqual(report.magic_packet, 'unknown')
        self.assertIn('не найден', wol.summary_text(report))

    def test_malformed_or_oversized_payload_is_rejected(self):
        for raw in ('garbage', '[]', '{}', self.payload(adapter=[]), ' ' * 65537):
            with self.subTest(raw=raw[:40]):
                with self.assertRaises(wol.WolSetupError):
                    wol.parse_diagnostics(raw)

    def test_probe_uses_fixed_script_no_shell_and_timeout(self):
        completed = subprocess.CompletedProcess([], 0, self.payload().encode('utf-8'), b'')
        with patch.object(wol, '_powershell', return_value='C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'), patch.object(wol.subprocess, 'run', return_value=completed) as run:
            report = wol.check_wol_readiness()
        self.assertEqual(report.magic_packet, 'enabled')
        args, kwargs = run.call_args
        self.assertFalse(kwargs['shell'])
        self.assertLessEqual(kwargs['timeout'], 20)
        self.assertIn('-EncodedCommand', args[0])
        self.assertNotIn('Set-Net', wol.DIAGNOSTIC_SCRIPT)
        self.assertNotIn('Start-Process', wol.DIAGNOSTIC_SCRIPT)
        self.assertIn('Get-NetAdapter -Physical', wol.DIAGNOSTIC_SCRIPT)
        self.assertIn('RouteMetric', wol.DIAGNOSTIC_SCRIPT)
        self.assertIn('InterfaceMetric', wol.DIAGNOSTIC_SCRIPT)

    def test_timeout_and_failed_probe_hide_raw_errors(self):
        for outcome in (subprocess.TimeoutExpired('secret', 20), OSError('secret')):
            with patch.object(wol, '_powershell', return_value='C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'), patch.object(wol.subprocess, 'run', side_effect=outcome):
                with self.assertRaises(wol.WolSetupError) as raised:
                    wol.check_wol_readiness()
                self.assertNotIn('secret', str(raised.exception))
        with patch.object(wol, '_powershell', return_value='C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'), patch.object(wol.subprocess, 'run',
                return_value=subprocess.CompletedProcess([], 1, b'', b'secret')):
            with self.assertRaises(wol.WolSetupError):
                wol.check_wol_readiness()

    def test_worker_emits_step_progress_and_final_report(self):
        results = queue.Queue()
        report = wol.parse_diagnostics(self.payload())
        with patch.object(wol, 'check_wol_readiness', return_value=report):
            worker = wol.start_diagnostics(results)
            worker.join(2)
        events = []
        while not results.empty():
            events.append(results.get_nowait())
        self.assertEqual(events[-1], ('done', report))
        self.assertEqual([e[1] for e in events if e[0] == 'progress'], [1, 2, 3])

    def test_worker_failure_does_not_emit_completion_progress(self):
        results = queue.Queue()
        with patch.object(wol, 'check_wol_readiness', side_effect=wol.WolSetupError('Недоступно')):
            worker = wol.start_diagnostics(results)
            worker.join(2)
        events = list(results.queue)
        self.assertEqual(events[-1], ('error', 'Недоступно'))
        self.assertNotIn(('progress', 3), events)

    def test_progress_text_includes_fraction_and_real_percentage(self):
        self.assertEqual(wol.progress_text(1, 'Проверка'), '1/3 · 33% · Проверка')
        self.assertEqual(wol.progress_text(2, 'Проверка'), '2/3 · 67% · Проверка')
        self.assertEqual(wol.progress_text(3, 'Готово'), '3/3 · 100% · Готово')

    def test_setup_timeout_explicitly_reports_unknown_and_possible_late_completion(self):
        with patch.object(wol, '_run_script', side_effect=wol.WolSetupError('timeout')):
            with self.assertRaises(wol.WolSetupError) as raised:
                wol.configure_windows('00000000-0000-0000-0000-000000000001', consent=True)
        self.assertIn('неизвест', str(raised.exception))
        self.assertIn('позднее', str(raised.exception))

    def test_setup_timeout_latches_uncertainty_and_blocks_later_attempt(self):
        with patch.object(wol, '_run_script', side_effect=wol.WolSetupError('timeout')) as run:
            with self.assertRaises(wol.WolSetupError):
                wol.configure_windows('00000000-0000-0000-0000-000000000001', consent=True)
            with self.assertRaises(wol.WolSetupError):
                wol.configure_windows('00000000-0000-0000-0000-000000000001', consent=True)
            self.assertEqual(run.call_count, 1)
        self.assertFalse(wol.setup_available())

    def test_setup_refuses_second_concurrent_request(self):
        wol._setup_lock.acquire()
        try:
            with patch.object(wol, '_run_script') as run:
                with self.assertRaises(wol.WolSetupError):
                    wol.configure_windows('00000000-0000-0000-0000-000000000001', consent=True)
                run.assert_not_called()
        finally:
            wol._setup_lock.release()

    def test_setup_requires_explicit_consent_and_strict_guid(self):
        with patch.object(wol, '_run_script') as run:
            for guid, consent in [('bad;exit', True), ('00000000-0000-0000-0000-000000000001', False)]:
                with self.assertRaises(wol.WolSetupError):
                    wol.configure_windows(guid, consent=consent)
            run.assert_not_called()

    def test_setup_script_only_changes_selected_pm_with_no_restart(self):
        script = wol.setup_script('00000000-0000-0000-0000-000000000001')
        self.assertIn('Set-NetAdapterPowerManagement -InputObject $pm[0] -WakeOnMagicPacket Enabled -NoRestart', script)
        self.assertIn("-ne 'Disabled'", script)
        self.assertIn('InterfaceGuid', script)
        self.assertIn('WildcardPattern', script)
        for forbidden in ('Set-ItemProperty', 'Restart-NetAdapter', 'WakeOnPattern Enabled', 'ExecutionPolicy', 'Invoke-Expression'):
            self.assertNotIn(forbidden, script)

    def test_setup_elevates_in_memory_and_rechecks_after_success(self):
        report = wol.parse_diagnostics(self.payload())
        with patch.object(wol, '_run_script', return_value=subprocess.CompletedProcess([], 0)) as run, \
                patch.object(wol, 'check_wol_readiness', return_value=report) as verify:
            result = wol.configure_windows(report.adapter_guid, consent=True)
        self.assertEqual(result, report)
        self.assertIn('-Verb RunAs -Wait -PassThru', run.call_args.args[0])
        self.assertIn('-EncodedCommand', run.call_args.args[0])
        self.assertNotIn('-File ', run.call_args.args[0])
        verify.assert_called_once()

    def test_setup_decline_and_unsupported_are_not_success(self):
        for code in (20, 21, 22, 23):
            with patch.object(wol, '_run_script', return_value=subprocess.CompletedProcess([], code)), \
                    patch.object(wol, 'check_wol_readiness') as verify:
                with self.assertRaises(wol.WolSetupError):
                    wol.configure_windows('00000000-0000-0000-0000-000000000001', consent=True)
                verify.assert_not_called()

    def test_setup_cannot_report_verified_setting_on_different_adapter(self):
        report = wol.WolReport('other', '00000000-0000-0000-0000-000000000002', 'enabled')
        with patch.object(wol, '_run_script', return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(wol, 'check_wol_readiness', return_value=report):
            with self.assertRaises(wol.WolSetupError):
                wol.configure_windows('00000000-0000-0000-0000-000000000001', consent=True)

    def test_embedded_page_unpacked_and_dispose_cancels_pending_timer(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with patch.object(wol, 'start_diagnostics'):
            page = wol.build_wol_page(root, 'unused')
        self.assertEqual(page.winfo_manager(), '')
        self.assertTrue(callable(page.dispose))
        page.dispose()
        self.assertFalse(page.winfo_exists())
        root.update()

    def test_bios_instructions_warn_about_hardware_and_manual_test(self):
        guide = wol.BIOS_GUIDE
        for term in ('BIOS', 'ErP', 'Wi-Fi', 'кабел', 'питани', 'вручную'):
            self.assertIn(term, guide)


if __name__ == '__main__':
    unittest.main()
