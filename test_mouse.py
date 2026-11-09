"""Mouse report and UI/worker boundary checks; no Bluetooth or input injection."""
import struct
import unittest
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from bluetooth_mouse import mouse_reports
from mouse_control import MouseController


class MouseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = MouseController('.')
        self.sent = []

        def send(command, **values):
            self.sent.append((command, values))
            return len(self.sent)

        self.controller.command = send
        self.controller._wanted_start = True
        self.controller._apply_status({'active':True,'ready':True,'reason':'ready'})

    def tearDown(self):
        self.controller._wanted_start = False
        self.controller._set_connected(False)
        self.controller.deleteLater()
        self.qt.processEvents()

    def acknowledge(self):
        self.controller._event({'type':'response','id':self.controller.input_id,'ok':True})
        self.qt.processEvents()

    def test_large_relative_movement_preserves_displacement(self):
        reports = [struct.unpack('Bbbb', r) for r in mouse_reports(1,2048,-2048,256)]
        self.assertEqual(tuple(sum(r[i] for r in reports) for i in (1,2,3)),(2048,-2048,256))
        self.assertTrue(all(r[0] == 1 for r in reports))

    def test_fast_click_survives_inflight_movement(self):
        self.controller.move(5,3)
        self.controller.buttons(1)
        self.controller.buttons(0)
        self.assertEqual(len(self.sent),1)
        self.acknowledge()
        self.assertEqual(self.sent[-1],('buttons',{'buttons':1}))
        self.acknowledge()
        self.assertEqual(self.sent[-1],('buttons',{'buttons':0}))

    def test_escape_discards_stale_motion_and_releases(self):
        self.controller.buttons(1)
        self.controller.move(300,100)
        self.controller.release()
        self.acknowledge()
        self.assertEqual(self.sent,[('buttons',{'buttons':1}),('buttons',{'buttons':0})])

    def test_large_move_is_split_before_worker_with_click_order_preserved(self):
        self.controller.move(1000,-300)
        self.controller.buttons(1)
        self.controller.buttons(0)
        while self.controller.input_id is not None:
            self.acknowledge()
        moves = [values for command, values in self.sent if command == 'move']
        self.assertEqual(sum(v['dx'] for v in moves),1000)
        self.assertEqual(sum(v['dy'] for v in moves),-300)
        self.assertTrue(all(abs(v['dx']) <= 127 and abs(v['dy']) <= 127 for v in moves))
        self.assertEqual(self.sent[-2:],[('buttons',{'buttons':1}),('buttons',{'buttons':0})])

    def test_escape_discards_large_move_remainder_inside_ui_queue(self):
        self.controller.move(1000,300)
        self.controller.release()
        self.acknowledge()
        self.assertEqual(self.sent,[('move',{'dx':127,'dy':127}),('buttons',{'buttons':0})])

    def test_unapproved_peer_cannot_receive_ui_input(self):
        self.controller._apply_status({'active':True,'ready':False,'subscribers':1,'reason':'unapproved_peer'})
        self.controller.move(10,10)
        self.controller.buttons(1)
        self.assertFalse(self.controller.connected)
        self.assertEqual(self.sent,[])

    def test_invalid_reports_are_rejected(self):
        for arguments in ((8,0,0,0),(1,True,0,0),(0,2049,0,0)):
            with self.assertRaises(ValueError):
                list(mouse_reports(*arguments))

    def test_late_mouse_error_during_lock_preserves_wake_channel(self):
        self.controller.move(5,3)
        input_id = self.controller.input_id
        self.controller._apply_status({'active':True,'ready':False,'wake_ready':True,'reason':'suspended'})
        self.controller._event({'type':'response','id':input_id,'ok':False,'error':'suspended'})
        self.assertTrue(self.controller.enabled)
        self.assertTrue(self.controller.wake_ready)
        self.assertFalse(self.controller.connected)
        self.assertEqual(self.sent[-1],('status',{}))
        self.assertNotIn(('stop',{}),self.sent)

    def test_wake_keeps_release_after_inflight_button_press(self):
        self.controller.wake_ready = True
        self.controller.buttons(1)
        self.controller.release()
        self.controller.wake()
        self.assertEqual(self.sent,[('buttons',{'buttons':1}),('buttons',{'buttons':0}),('wake',{})])

    def test_library_warning_does_not_replace_connected_status(self):
        message = self.controller.message
        recorded = []
        self.controller.log = recorded.append
        self.controller.process = SimpleNamespace(readAllStandardError=lambda: b'DeprecationWarning: use notify_value_async() instead')
        self.controller._stderr()
        self.assertEqual(self.controller.message,message)
        self.assertTrue(self.controller.connected)
        self.assertIn('DeprecationWarning',recorded[0])


if __name__ == '__main__':
    unittest.main()
