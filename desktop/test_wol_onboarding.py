"""First-pairing completion is local, fail-closed and never a wake proof."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop import wol_setup as wol
try:
    from desktop import wol_onboarding as onboarding
except ImportError:
    onboarding = None

GUID = '00000000-0000-0000-0000-000000000001'
OTHER = '00000000-0000-0000-0000-000000000002'


class OnboardingPageTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.tk = tk
        self.assertIsNotNone(onboarding)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.events = []
        self.queue = None
        def start(results):
            self.queue = results
        self.start = patch.object(wol, 'start_diagnostics', side_effect=start)
        self.start.start()
        self.addCleanup(self.start.stop)

    def widgets(self, parent):
        for child in parent.winfo_children():
            yield child
            yield from self.widgets(child)

    def button(self, text):
        from tkinter import ttk
        return next(w for w in self.widgets(self.page) if isinstance(w, ttk.Button) and w.cget('text') == text)

    def deliver(self, report):
        self.queue.put(('done', report))
        # Execute the page's owned poll timer without sleeping or real PowerShell.
        for timer in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
            command = self.root.tk.call('after', 'info', timer)[0]
            self.root.tk.call('after', 'cancel', timer)
            self.root.tk.call(command)

    def build(self):
        self.page = onboarding.build_onboarding_page(self.root, self.data, lambda: self.events.append('paired'))

    def test_invalid_windows_states_cannot_continue_or_persist(self):
        self.build()
        for state in ('unknown', 'disabled', 'unsupported'):
            self.deliver(wol.WolReport('Ethernet', GUID, state))
            self.button('Продолжить сопряжение').invoke()
            self.assertEqual(self.events, [])
            self.assertFalse((self.data / 'wol_onboarding.json').exists())
            self.button('Повторить проверку').invoke()
        self.page.dispose()

    def test_first_completion_requires_two_checkboxes_and_explicit_continue(self):
        from tkinter import ttk
        self.build()
        self.deliver(wol.WolReport('Ethernet', GUID, 'enabled'))
        self.button('Проверить и завершить настройку').invoke()
        self.assertFalse((self.data / 'wol_onboarding.json').exists())
        for widget in self.widgets(self.page):
            if isinstance(widget, ttk.Checkbutton):
                widget.invoke()
        import threading
        workers = []
        original = threading.Thread
        def start_worker(*args, **kwargs):
            thread = original(*args, **kwargs)
            workers.append(thread)
            return thread
        with patch.object(wol, 'check_wol_readiness', return_value=wol.WolReport('Ethernet', GUID, 'enabled')), patch.object(threading, 'Thread', side_effect=start_worker):
            self.button('Проверить и завершить настройку').invoke()
            for worker in workers:
                worker.join(2)
        self.deliver(wol.WolReport('Ethernet', GUID, 'enabled'))
        self.assertTrue((self.data / 'wol_onboarding.json').exists())
        self.assertEqual(self.events, [])
        self.button('Продолжить сопряжение').invoke()
        self.assertEqual(self.events, ['paired'])

    def test_newer_disabled_report_rejects_older_successful_save_result(self):
        import threading
        from tkinter import ttk
        self.build()
        self.deliver(wol.WolReport('Ethernet', GUID, 'enabled'))
        for widget in self.widgets(self.page):
            if isinstance(widget, ttk.Checkbutton):
                widget.invoke()
        work = []
        class DeferredThread:
            def __init__(self, *, target, **kwargs):
                work.append(target)
            def start(self):
                pass
        with patch.object(threading, 'Thread', DeferredThread):
            self.button('Проверить и завершить настройку').invoke()
        self.button('Повторить проверку').invoke()
        self.deliver(wol.WolReport('Ethernet', GUID, 'disabled'))
        with patch.object(wol, 'check_wol_readiness', return_value=wol.WolReport('Ethernet', GUID, 'enabled')):
            work[0]()
        self.deliver(wol.WolReport('Ethernet', GUID, 'disabled'))
        self.button('Продолжить сопряжение').invoke()
        self.assertEqual(self.events, [], 'older save cannot override a newer disabled report')

    def test_saved_matching_completion_bypasses_setup_after_explicit_fresh_check(self):
        with patch.object(onboarding.wol, 'check_wol_readiness', return_value=wol.WolReport('Ethernet', GUID, 'enabled')):
            onboarding.complete_onboarding(self.data, adapter_guid=GUID, bios_manual_ack=True, network_compatible=True)
        self.build()
        self.assertEqual(self.events, [])
        self.deliver(wol.WolReport('Ethernet', GUID, 'enabled'))
        self.assertEqual(self.events, ['paired'])

    def test_changed_adapter_requires_setup_again_and_disposal_ignores_late_result(self):
        with patch.object(onboarding.wol, 'check_wol_readiness', return_value=wol.WolReport('Ethernet', GUID, 'enabled')):
            onboarding.complete_onboarding(self.data, adapter_guid=GUID, bios_manual_ack=True, network_compatible=True)
        self.build()
        self.deliver(wol.WolReport('Other', OTHER, 'enabled'))
        self.assertEqual(self.events, [])
        self.page.dispose()
        self.queue.put(('done', wol.WolReport('Ethernet', GUID, 'enabled')))
        self.root.update()
        self.assertEqual(self.events, [])


class OnboardingRecordTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(onboarding, 'mandatory onboarding module must exist')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.record = self.data / 'wol_onboarding.json'

    def complete(self, **overrides):
        args = dict(adapter_guid=GUID, bios_manual_ack=True, network_compatible=True)
        args.update(overrides)
        return onboarding.complete_onboarding(self.data, **args)

    def test_fresh_enabled_and_acknowledged_saves_private_atomic_completion(self):
        report = wol.WolReport('Ethernet', GUID, 'enabled')
        with patch.object(onboarding.wol, 'check_wol_readiness', return_value=report):
            self.complete()
        self.assertEqual(json.loads(self.record.read_text('utf-8')), {
            'schema': 1, 'adapter_guid': GUID, 'bios_manual_ack': True,
            'network_compatible': True, 'completed': True})
        self.assertEqual(list(self.data.iterdir()), [self.record])
        self.assertTrue(onboarding.matches_completion(onboarding.load_completion(self.data), report))
        self.assertFalse(report.wake_verified)

    def test_disabled_unknown_unsupported_missing_or_changed_adapter_never_save(self):
        reports = [wol.WolReport('Ethernet', GUID, value) for value in ('disabled', 'unknown', 'unsupported')]
        reports += [wol.WolReport(), wol.WolReport('Other', OTHER, 'enabled')]
        for report in reports:
            with self.subTest(report=report), patch.object(onboarding.wol, 'check_wol_readiness', return_value=report):
                with self.assertRaises(wol.WolSetupError):
                    self.complete()
                self.assertFalse(self.record.exists())

    def test_missing_ack_invalid_guid_and_failed_check_never_save(self):
        for changes in ({'bios_manual_ack': False}, {'network_compatible': False},
                        {'bios_manual_ack': 1}, {'adapter_guid': 'not-guid'}):
            with self.subTest(changes=changes), patch.object(onboarding.wol, 'check_wol_readiness', side_effect=AssertionError('must validate first')):
                with self.assertRaises(wol.WolSetupError):
                    self.complete(**changes)
        with patch.object(onboarding.wol, 'check_wol_readiness', side_effect=wol.WolSetupError('cancelled')):
            with self.assertRaises(wol.WolSetupError):
                self.complete()
        self.assertFalse(self.record.exists())

    def test_malformed_unbounded_and_non_boolean_records_fail_closed_without_probe(self):
        valid = {'schema': 1, 'adapter_guid': GUID, 'bios_manual_ack': True,
                 'network_compatible': True, 'completed': True}
        bad = ['[]', '{', ' ' * 4097]
        for key, value in [('schema', True), ('schema', 2), ('adapter_guid', 'bad'),
                           ('completed', 1), ('bios_manual_ack', False), ('network_compatible', False)]:
            bad.append(json.dumps(dict(valid, **{key: value})))
        with patch.object(onboarding.wol, 'check_wol_readiness', side_effect=AssertionError('load must not probe')):
            self.assertIsNone(onboarding.load_completion(self.data))
            for raw in bad:
                self.record.write_text(raw, encoding='utf-8')
                self.assertIsNone(onboarding.load_completion(self.data), raw[:80])

    def test_cancel_during_fresh_check_never_persists_completion(self):
        import threading
        cancelled = threading.Event()
        def probe():
            cancelled.set()
            return wol.WolReport('Ethernet', GUID, 'enabled')
        with patch.object(onboarding.wol, 'check_wol_readiness', side_effect=probe):
            with self.assertRaises(wol.WolSetupError):
                onboarding.complete_onboarding(self.data, adapter_guid=GUID, bios_manual_ack=True,
                                               network_compatible=True, cancelled=cancelled)
        self.assertFalse(self.record.exists())

    def test_atomic_replace_failure_preserves_previous_record_and_cleans_temp(self):
        self.record.write_text('previous', encoding='utf-8')
        with patch.object(onboarding.wol, 'check_wol_readiness', return_value=wol.WolReport('Ethernet', GUID, 'enabled')), patch.object(onboarding.os, 'replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(wol.WolSetupError):
                self.complete()
        self.assertEqual(self.record.read_text('utf-8'), 'previous')
        self.assertEqual(list(self.data.iterdir()), [self.record])

    def test_saved_completion_does_not_match_changed_or_unready_adapter(self):
        record = {'schema': 1, 'adapter_guid': GUID, 'bios_manual_ack': True,
                  'network_compatible': True, 'completed': True}
        for report in (wol.WolReport('Other', OTHER, 'enabled'), wol.WolReport('Ethernet', GUID, 'disabled'), wol.WolReport()):
            self.assertFalse(onboarding.matches_completion(record, report))
