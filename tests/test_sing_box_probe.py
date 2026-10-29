"""Deep probe tests use only local servers, never public test endpoints."""
import copy
import os
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import shutil
import socket
import struct
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("probe", ROOT / "dot_config/sing-box/probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTest(unittest.TestCase):
    def setUp(self):
        probe.STOP.clear()

    def test_quick_api_auth_defaults_override_and_no_secret(self):
        for secret in [None, 'custom-api-secret', '']:
            with self.subTest(secret=secret), patch.dict(os.environ, {}, clear=True):
                if secret is not None:
                    os.environ['SB_API_SECRET'] = secret
                with patch.object(probe, 'curl', return_value='{"delay": 12}') as curl:
                    self.assertEqual(probe.quick('vpn / test')['latency_ms'], 12)
                args = curl.call_args.args
                if secret == '':
                    self.assertNotIn('--header', args)
                else:
                    self.assertIn('Authorization: Bearer ' + (secret or 'admin'), args)
                self.assertEqual(args[-1], 'http://127.0.0.1:9091/proxies/vpn%20%2F%20test/delay')

    def test_isolated_config_keeps_dependencies_without_production_listeners(self):
        config = {
            "experimental": {"cache_file": {"enabled": True}},
            "services": [{"type": "resolved"}],
            "inbounds": [{"type": "tun"}],
            "dns": {"servers": [{"type": "local", "tag": "local"}]},
            "route": {"rules": [{"outbound": "direct"}], "rule_set": [{"tag": "remote"}],
                      "default_domain_resolver": "local", "final": "proxy"},
            "outbounds": [{"tag": "proxy", "type": "urltest", "outbounds": ["exit"],
                           "url": "https://example.org", "interval": "1m", "tolerance": 50,
                           "idle_timeout": "30m"},
                          {"tag": "exit", "type": "socks", "detour": "hop"},
                          {"tag": "hop", "type": "ssh"}],
        }
        original = copy.deepcopy(config)
        isolated = probe.isolated_config(config, "exit", 12345)
        self.assertEqual(config, original)
        self.assertNotIn('experimental', isolated)
        self.assertNotIn('services', isolated)
        self.assertEqual(isolated['inbounds'], [{'type': 'socks', 'listen': '127.0.0.1', 'listen_port': 12345}])
        self.assertEqual(isolated['route'], {'default_domain_resolver': 'local', 'final': 'exit'})
        self.assertEqual(isolated['outbounds'][0], {'tag': 'proxy', 'type': 'selector', 'outbounds': ['exit']})
        self.assertEqual(isolated['outbounds'][1]['detour'], 'hop')
        self.assertEqual(isolated['dns'], config['dns'])

    def test_stability_keeps_late_timeouts(self):
        with patch.object(probe, 'transfer', side_effect=[{'time_total': 0.1}, RuntimeError('timeout'), RuntimeError('timeout')]), \
             patch.object(probe.STOP, 'wait', return_value=False) as wait:
            result = probe.stability(1234, 3)
        self.assertEqual(wait.call_count, 2)
        self.assertEqual(result['status'], 'unstable')
        self.assertEqual(result['successes'], 1)
        self.assertEqual(result['attempts'], 3)
        self.assertEqual(result['min_latency_ms'], 100)
        self.assertEqual(result['median_latency_ms'], 100)
        self.assertEqual(result['max_latency_ms'], 100)
        self.assertIn('timeout', result['samples'][-1]['error'])
        self.assertNotEqual(result['samples'][0]['target'], result['samples'][1]['target'])

    def test_stability_timing_statistics_exclude_failed_attempts(self):
        for times, expected_median in [([0.1, 0.9, 0.2], 200), ([0.1, 0.9, 0.2, 0.3], 250)]:
            with self.subTest(times=times):
                outcomes = [{'time_total': value} for value in times] + [RuntimeError('timeout')]
                with patch.object(probe, 'transfer', side_effect=outcomes), \
                     patch.object(probe.STOP, 'wait', return_value=False):
                    result = probe.stability(1234, len(outcomes))
                self.assertEqual(result['min_latency_ms'], 100)
                self.assertEqual(result['median_latency_ms'], expected_median)
                self.assertEqual(result['max_latency_ms'], 900)
                self.assertEqual(result['successes'], len(times))
                self.assertEqual(result['attempts'], len(outcomes))

    def test_stability_attempt_count_is_independent_of_latency_and_failures(self):
        for outcome in [{'time_total': 0.01}, {'time_total': 14.9}, RuntimeError('timeout')]:
            with self.subTest(outcome=outcome):
                kwargs = {'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': outcome}
                with patch.object(probe, 'transfer', **kwargs) as transfer, \
                     patch.object(probe.STOP, 'wait', return_value=False) as wait:
                    result = probe.stability(1234, 5)
                self.assertEqual(transfer.call_count, 5)
                self.assertEqual(result['attempts'], 5)
                self.assertEqual(len(result['samples']), 5)
                self.assertEqual(wait.call_count, 4)
                self.assertEqual(result['successes'], 0 if isinstance(outcome, Exception) else 5)
                if isinstance(outcome, Exception):
                    for statistic in ['min', 'median', 'max']:
                        self.assertIsNone(result[f'{statistic}_latency_ms'])

    def test_stability_single_attempt_does_not_pause_and_cancellation_stops(self):
        with patch.object(probe, 'transfer', return_value={'time_total': 0.1}) as transfer, \
             patch.object(probe.STOP, 'wait', return_value=True) as wait:
            self.assertEqual(probe.stability(1234, 1)['attempts'], 1)
            wait.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                probe.stability(1234, 5)
            self.assertEqual(transfer.call_count, 2)
            wait.assert_called_once_with(1)

    def test_bandwidth_measures_both_directions_and_keeps_partial_failures(self):
        with patch.object(probe, 'transfer', side_effect=[{'time_total': 2, 'size_download': 1000000}, RuntimeError('upload timeout')]):
            result = probe.bandwidth(1234, 1000000)
        self.assertEqual(result['download']['mbps'], 4)
        self.assertEqual(result['upload']['status'], 'failed')
        self.assertEqual(result['status'], 'failed')
        with patch.object(probe, 'transfer', return_value={'time_total': 2, 'size_download': 1, 'size_upload': 1}):
            result = probe.bandwidth(1234, 100)
        self.assertIn('incomplete', result['download']['error'])
        self.assertIn('incomplete', result['upload']['error'])

    def test_udp_keeps_loss_and_unsupported_errors(self):
        with patch.object(probe, 'stun', side_effect=[10, 20, OSError('timed out'), 30, 40, 50]):
            result = probe.udp_probe(1234)
        self.assertEqual(result['status'], 'degraded')
        self.assertEqual((result['sent'], result['received']), (6, 5))
        self.assertEqual(result['loss_percent'], 16.7)
        self.assertEqual(result['rtt_spread_ms'], 40)
        with patch.object(probe, 'stun', side_effect=RuntimeError('UDP ASSOCIATE rejected')):
            result = probe.udp_probe(1234)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['received'], 0)

    def test_full_keeps_other_checks_after_udp_failure(self):
        args = SimpleNamespace(mode='full', attempts=20, bytes=100)
        with patch.object(probe, 'instance', return_value=nullcontext(1234)), \
             patch.object(probe, 'udp_probe', return_value={'status': 'failed'}) as udp, \
             patch.object(probe, 'stability', return_value={'status': 'passed'}) as stability, \
             patch.object(probe, 'bandwidth', return_value={'status': 'passed'}) as bandwidth:
            result = probe.probe('exit', {}, args)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['stability']['status'], 'passed')
        self.assertEqual(result['bandwidth']['status'], 'passed')
        udp.assert_called_once_with(1234)
        stability.assert_called_once_with(1234, 20)
        bandwidth.assert_called_once_with(1234, 100)

    @unittest.skipUnless(shutil.which('sing-box') and shutil.which('curl'), 'requires sing-box and curl')
    def test_real_isolated_instance_tcp_udp_and_cleanup(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', '4')
                self.end_headers()
                self.wfile.write(b'test')

            def log_message(self, *_):
                pass

        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
            server.bind(('127.0.0.1', 0))
            server.settimeout(5)
            errors = []

            def reply():
                try:
                    for valid in (True, False):
                        request, peer = server.recvfrom(4096)
                        attribute = struct.pack('!HHBBH4s', 0x0020, 8, 0, 1, 1234, b'\x7f\x00\x00\x01')
                        transaction = request[8:20] if valid else b'wrong-id!!!!'
                        server.sendto(struct.pack('!HHI', 0x0101, len(attribute), 0x2112A442) + transaction + attribute, peer)
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=reply, daemon=True)
            worker.start()
            config = {'outbounds': [{'type': 'direct', 'tag': 'exit'}]}
            with probe.instance(config, 'exit') as port:
                data = probe.transfer(port, f'http://127.0.0.1:{http.server_port}/')
                self.assertEqual(data['size_download'], 4)
                self.assertGreaterEqual(probe.stun(port, '127.0.0.1', server.getsockname()[1]), 0)
                with self.assertRaisesRegex(RuntimeError, 'invalid STUN'):
                    probe.stun(port, '127.0.0.1', server.getsockname()[1])
            worker.join(timeout=5)
            self.assertFalse(errors)
            self.assertFalse(worker.is_alive())
            with self.assertRaises(OSError):
                socket.create_connection(('127.0.0.1', port), timeout=0.2)


if __name__ == '__main__':
    unittest.main()
