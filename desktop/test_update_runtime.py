import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


class RuntimeUpdateTests(unittest.TestCase):
    def test_named_shutdown_shared_by_exact_install_path_only(self):
        h = importlib.import_module('update_helper')
        self.assertEqual(h.event_name(Path('C:/apps/DroidBridge.exe')), h.event_name(Path('C:/apps/DroidBridge.exe')))
        self.assertNotEqual(h.event_name(Path('C:/apps/DroidBridge.exe')), h.event_name(Path('C:/other/DroidBridge.exe')))

    def test_native_event_roundtrip_no_process_termination(self):
        runtime = importlib.import_module('runtime')
        first = runtime.UpdateShutdownSignal('Local\\DroidBridge-test-updater-safe')
        second = runtime.UpdateShutdownSignal('Local\\DroidBridge-test-updater-safe')
        try:
            self.assertFalse(first.is_set())
            second.set()
            self.assertTrue(first.is_set())
            first.reset()
            self.assertFalse(second.is_set())
        finally:
            first.close()
            second.close()

    def test_server_shutdown_drains_requests(self):
        runtime = importlib.import_module('runtime')
        class FakeServer:
            daemon_threads = True
            def serve_forever(self):
                return 'served'
            def shutdown(self):
                pass
        class Module:
            Server = FakeServer
        class Signal:
            def wait(self, timeout):
                return False
        runtime.coordinate_component_shutdown(Module, 'server', Signal())
        self.assertFalse(Module.Server.daemon_threads)
        self.assertEqual(Module.Server().serve_forever(), 'served')

    def test_self_test_imports_without_network_and_component_skips_gui(self):
        import launcher
        with patch.object(sys, 'argv', ['launcher', '--component', 'server']), patch.object(launcher, 'run_component', return_value=0) as run, patch('update_manager.start_startup_check') as check:
            self.assertEqual(launcher.main(), 0)
            run.assert_called_once_with('server', [])
            check.assert_not_called()


if __name__ == '__main__':
    unittest.main()
