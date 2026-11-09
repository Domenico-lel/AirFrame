"""No-radio tests for the experimental Home/wake report and peer boundaries."""
import asyncio
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bluetooth_mouse import MouseWorker, REPORT_MAP, HOME_PRESS, HOME_RELEASE, HID_INFORMATION


def client(identifier):
    return SimpleNamespace(session=SimpleNamespace(device_id=SimpleNamespace(id=identifier)))


class Report:
    def __init__(self, *identifiers):
        self.subscribed_clients = [client(identifier) for identifier in identifiers]
        self.calls = []
        self.fail_on = set()

    async def notify_value_async(self, payload, recipient):
        self.calls.append((bytes(payload), recipient.session.device_id.id))
        return SimpleNamespace(status='failed' if len(self.calls) in self.fail_on else 'ok')


class PeerDevice:
    def __init__(self, connected=True):
        self.name = 'Test phone'
        self.connection_status = SimpleNamespace(name='CONNECTED' if connected else 'DISCONNECTED')
        self.callbacks = {}
        self.closed = False
        self.interval_units = 24

    def get_connection_parameters(self):
        return SimpleNamespace(connection_interval=self.interval_units)

    def add_connection_status_changed(self, callback):
        self.callbacks[1] = callback
        return 1

    def remove_connection_status_changed(self, token):
        del self.callbacks[token]

    def close(self):
        self.closed = True

    def set_connected(self, connected):
        self.connection_status = SimpleNamespace(name='CONNECTED' if connected else 'DISCONNECTED')
        for callback in tuple(self.callbacks.values()):
            callback(self, None)


def worker(mouse=('phone',), consumer=('phone',), suspended=False):
    # Bypass __init__: absolutely no WinRT API, device discovery, or advertising.
    result = MouseWorker.__new__(MouseWorker)
    result.report = Report(*mouse)
    result.consumer_report = Report(*consumer)
    result.provider = SimpleNamespace(advertisement_status=SimpleNamespace(name='STARTED'))
    result.providers = [result.provider]
    result.gatt = SimpleNamespace(GattCommunicationStatus=SimpleNamespace(SUCCESS='ok'))
    result.buffer = bytes
    result.active = True
    result.starting = False
    result.suspended = suspended
    result.peer_id = 'phone'
    result.peer_name = 'Test phone'
    result.peer_device = PeerDevice()
    result.peer_device_handler = None
    result.peer_lookup = None
    result.link_connected = True
    result.expected_peer = None
    result.last_status = None
    result.loop = asyncio.get_running_loop()
    result.last_mouse_notify = None
    result.mouse_notify_lock = asyncio.Lock()
    result.callback_tasks = set()
    result.buttons = 0
    result.generation = 4
    result.consumer_target = None
    return result


class WakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_mouse_interval_uses_negotiated_units_with_safe_fallback(self):
        w = worker()
        for units, expected_ms in ((6, 16.667), (12, 16.667), (24, 30), (40, 50), (0, 30)):
            w.peer_device.interval_units = units
            self.assertAlmostEqual(w._mouse_notification_interval() * 1000, expected_ms, places=2)
            self.assertEqual(w.status()['diagnostics']['mouse_notify_interval_ms'], expected_ms)
        w.peer_device.get_connection_parameters = None  # Older SDK projection.
        self.assertEqual(w._mouse_notification_interval(), .030)
        self.assertIsNone(w.status()['diagnostics']['mouse_connection_interval_ms'])

    async def test_split_moves_pace_each_report_and_preserve_button_edges(self):
        w = worker()
        now = [10.0]
        times = []
        w.loop = SimpleNamespace(time=lambda: now[0])
        original_notify = w.report.notify_value_async

        async def notify(payload, recipient):
            times.append(now[0])
            return await original_notify(payload, recipient)

        async def wait(delay):
            now[0] += delay

        w.report.notify_value_async = notify
        with patch('bluetooth_mouse.asyncio.sleep', side_effect=wait):
            await w.input('buttons', {'buttons': 1})
            await w.input('move', {'dx': 400, 'dy': -300})
            await w.input('buttons', {'buttons': 0})
        reports = [struct.unpack('Bbbb', payload) for payload, peer in w.report.calls]
        self.assertEqual(len(reports), 6)  # Press, four separate chunks, release.
        self.assertEqual([r[0] for r in reports], [1, 1, 1, 1, 1, 0])
        self.assertEqual(tuple(sum(r[i] for r in reports) for i in (1, 2)), (400, -300))
        self.assertTrue(all(b - a >= .030 - 1e-8 for a, b in zip(times, times[1:])))
        self.assertGreaterEqual(times[-1] - times[0], .15 - 1e-8)
        self.assertEqual(w.buttons, 0)

    async def test_disconnect_or_stop_during_pacing_prevents_late_report(self):
        for action in ('disconnect', 'stop'):
            w = worker()
            w.loop = SimpleNamespace(time=lambda: 10.0)
            await w.input('move', {'dx': 1, 'dy': 0})

            async def wait(delay):
                if action == 'disconnect':
                    w.peer_device.connection_status = SimpleNamespace(name='DISCONNECTED')
                else:
                    w.active = False
                    w.generation += 1

            with patch('bluetooth_mouse.asyncio.sleep', side_effect=wait), patch('bluetooth_mouse.emit'):
                with self.assertRaises(RuntimeError):
                    await w.input('buttons', {'buttons': 1})
            self.assertEqual(len(w.report.calls), 1)
            self.assertEqual(w.buttons, 0)

    async def test_peer_lifetime_reset_clears_notification_deadline(self):
        w = worker()
        w.last_mouse_notify = w.loop.time()
        w._release_peer_device()
        self.assertIsNone(w.last_mouse_notify)

    async def test_retains_peer_and_blocks_cached_subscriptions_on_disconnect(self):
        w = worker()
        device = PeerDevice()
        w.peer_device = None
        w.link_connected = None
        w.Device = SimpleNamespace(from_id_async=AsyncMock(return_value=device))
        with patch('bluetooth_mouse.emit') as emitted:
            await w._subscriptions_changed()
            self.assertIs(w.peer_device, device)
            self.assertFalse(device.closed)
            self.assertTrue(w.status()['link_connected'])
            self.assertTrue(w.status()['ready'])
            w.buttons = 1
            device.set_connected(False)
            await asyncio.sleep(.01)
            state = w.status()
            self.assertEqual((state['subscribers'], state['wake_subscribers']), (1, 1))
            self.assertFalse(state['link_connected'])
            self.assertFalse(state['ready'])
            self.assertFalse(state['wake_ready'])
            self.assertEqual(state['reason'], 'link_disconnected')
            self.assertEqual(w.buttons, 0)
            self.assertEqual(w.peer_id, 'phone')
            self.assertFalse(emitted.call_args.args[0]['link_connected'])
            with self.assertRaises(RuntimeError):
                await w.wake()
            with self.assertRaises(RuntimeError):
                await w.input('move', {'dx': 1, 'dy': 0})
            self.assertEqual(w.report.calls, [])
            self.assertEqual(w.consumer_report.calls, [])

            device.set_connected(True)
            await asyncio.sleep(.01)
            self.assertTrue(w.status()['ready'])
            self.assertTrue(w.status()['wake_ready'])
            self.assertFalse(device.closed)
            self.assertEqual(w.peer_id, 'phone')

    async def test_status_snapshot_catches_disconnect_without_event(self):
        w = worker()
        w.buttons = 1
        w.peer_device.connection_status = SimpleNamespace(name='DISCONNECTED')
        self.assertEqual(w.status()['reason'], 'link_disconnected')
        self.assertFalse(w.status()['wake_ready'])
        self.assertEqual(w.buttons, 0)

    async def test_unavailable_peer_lookup_remains_explicitly_unknown(self):
        for response in (None, RuntimeError('lookup unavailable')):
            w = worker()
            w.peer_device = None
            w.link_connected = None
            lookup = AsyncMock(side_effect=response) if isinstance(response, Exception) else AsyncMock(return_value=None)
            w.Device = SimpleNamespace(from_id_async=lookup)
            with patch('bluetooth_mouse.emit'):
                await w._subscriptions_changed()
            self.assertIsNone(w.status()['link_connected'])
            self.assertTrue(w.status()['ready'])
            self.assertIsNone(w.peer_lookup)

    async def test_late_connection_callbacks_and_lookup_cannot_restore_old_peer(self):
        w = worker()
        old_device = PeerDevice(False)
        current_device = w.peer_device
        w.link_connected = True
        with patch('bluetooth_mouse.emit') as emitted:
            await w._peer_connection_changed(old_device, w.generation, w.peer_id)
            current_device.connection_status = SimpleNamespace(name='DISCONNECTED')
            await w._peer_connection_changed(current_device, w.generation - 1, w.peer_id)
            self.assertTrue(w.link_connected)
            emitted.assert_not_called()

        w.peer_device = None
        w.link_connected = None
        lookup_started = asyncio.Event()
        finish_lookup = asyncio.Event()

        async def lookup(peer_id):
            lookup_started.set()
            await finish_lookup.wait()
            return old_device

        w.Device = SimpleNamespace(from_id_async=lookup)
        pending = asyncio.create_task(w._retain_peer_device('phone'))
        await lookup_started.wait()
        w.generation += 1
        w.peer_device = current_device
        finish_lookup.set()
        await pending
        self.assertTrue(old_device.closed)
        self.assertIs(w.peer_device, current_device)
        self.assertFalse(current_device.closed)

    async def test_drop_services_removes_peer_handler_and_closes_reference(self):
        w = worker()
        device = PeerDevice()
        w.peer_device = None
        w.Device = SimpleNamespace(from_id_async=AsyncMock(return_value=device))
        await w._retain_peer_device('phone')
        callback = device.callbacks[1]
        w.handlers = []
        w.published = set()
        w._drop_services()
        self.assertTrue(device.closed)
        self.assertEqual(device.callbacks, {})
        self.assertIsNone(w.peer_device)
        self.assertIsNone(w.link_connected)
        with patch('bluetooth_mouse.emit') as emitted:
            callback(device, None)
            await asyncio.sleep(.01)
            emitted.assert_not_called()

    async def test_input_diagnostics_count_without_retaining_input_values(self):
        w = worker()
        await w.input('move', {'dx': 4, 'dy': -2})
        await w.input('buttons', {'buttons': 1})
        await w.input('release', {})
        diagnostics = w.status()['diagnostics']
        self.assertEqual(diagnostics['mouse_move_commands'], 1)
        self.assertEqual(diagnostics['mouse_button_commands'], 1)
        self.assertEqual(diagnostics['mouse_nonzero_reports_attempted'], 2)
        self.assertEqual(diagnostics['mouse_notify_accepted'], 3)

    async def test_home_can_wake_suspended_peer_but_mouse_remains_blocked(self):
        w = worker(suspended=True)
        state = w.status()
        self.assertTrue(state['wake_ready'])
        self.assertFalse(state['ready'])
        result = await w.command({'command':'wake'})
        self.assertEqual(result, {'sent':True,'effect':'unverified','action':'home','reports':2})
        self.assertEqual(w.consumer_report.calls,[(HOME_PRESS,'phone'),(HOME_RELEASE,'phone')])
        with self.assertRaises(RuntimeError):
            await w.input('move',{'dx':1,'dy':1})
        self.assertEqual(w.report.calls,[])
        self.assertTrue(w.suspended)  # Sending Home must not invent host resume.

    async def test_consumer_only_same_peer_can_receive_home(self):
        w = worker(mouse=(),suspended=True)
        self.assertTrue(w.status()['wake_ready'])
        self.assertFalse(w.status()['ready'])
        await w.wake()
        self.assertEqual(len(w.consumer_report.calls),2)

    async def test_missing_multiple_and_cross_report_peers_are_rejected(self):
        cases = [worker(consumer=()), worker(consumer=('phone','other')),
                 worker(mouse=('other',)), worker(consumer=('other',))]
        for w in cases:
            self.assertFalse(w.status()['wake_ready'])
            with self.assertRaises(RuntimeError):
                await w.wake()
            self.assertEqual(w.consumer_report.calls,[])

    async def test_inactive_or_unpinned_peer_cannot_receive_home(self):
        for state in ('inactive','unpinned','not_advertising'):
            w = worker()
            if state == 'inactive':
                w.active = False
            elif state == 'unpinned':
                w.peer_id = None
            else:
                w.provider.advertisement_status = SimpleNamespace(name='ABORTED')
            with self.assertRaises(RuntimeError):
                await w.wake()
            self.assertEqual(w.consumer_report.calls,[])

    async def test_uncertain_press_failure_attempts_release_without_press_retry(self):
        w = worker()
        w.consumer_report.fail_on = {1}
        with self.assertRaises(RuntimeError):
            await w.wake()
        self.assertEqual(w.consumer_report.calls,[(HOME_PRESS,'phone'),(HOME_RELEASE,'phone')])
        self.assertIsNone(w.consumer_target)

    async def test_failed_release_only_retries_release(self):
        w = worker()
        w.consumer_report.fail_on = {2}
        with self.assertRaises(RuntimeError):
            await w.wake()
        self.assertEqual(w.consumer_report.calls,
                         [(HOME_PRESS,'phone'),(HOME_RELEASE,'phone'),(HOME_RELEASE,'phone')])
        self.assertIsNone(w.consumer_target)

    async def test_release_stays_on_original_peer_if_second_peer_appears(self):
        w = worker()
        original = w.consumer_report.notify_value_async

        async def notify(payload, recipient):
            answer = await original(payload, recipient)
            if payload == HOME_PRESS:
                w.consumer_report.subscribed_clients.append(client('other'))
            return answer

        w.consumer_report.notify_value_async = notify
        await w.wake()
        self.assertEqual(w.consumer_report.calls,[(HOME_PRESS,'phone'),(HOME_RELEASE,'phone')])
        self.assertFalse(w.status()['wake_ready'])

    async def test_hold_interval_is_short_and_result_does_not_claim_wake(self):
        w = worker()
        start = asyncio.get_running_loop().time()
        result = await w.wake()
        elapsed = asyncio.get_running_loop().time()-start
        self.assertGreaterEqual(elapsed,.07)
        self.assertLess(elapsed,.5)
        self.assertNotIn('awake',result)
        self.assertNotIn('unlocked',result)

    def test_descriptor_payload_sizes_match_reports(self):
        # Decode HID short items to check declared input bit lengths per report.
        offset = 0
        report_id = 0
        report_size = report_count = 0
        lengths = {}
        while offset < len(REPORT_MAP):
            prefix = REPORT_MAP[offset]
            offset += 1
            size = (0,1,2,4)[prefix & 3]
            value = int.from_bytes(REPORT_MAP[offset:offset+size],'little')
            offset += size
            tag, kind = prefix >> 4, (prefix >> 2) & 3
            if kind == 1:
                if tag == 7:
                    report_size = value
                elif tag == 8:
                    report_id = value
                elif tag == 9:
                    report_count = value
            elif kind == 0 and tag == 8:
                lengths[report_id] = lengths.get(report_id,0)+report_size*report_count
        self.assertEqual(lengths,{1:32,2:16})
        self.assertEqual(len(HOME_PRESS)*8,lengths[2])
        self.assertEqual(HOME_PRESS,b'\x40\x00')
        self.assertEqual(HOME_RELEASE,b'\x00\x00')
        self.assertEqual(HID_INFORMATION[-1] & 3,3)


if __name__ == '__main__':
    unittest.main()
