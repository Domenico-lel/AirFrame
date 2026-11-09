"""Run with QT_QPA_PLATFORM=offscreen python -m unittest test_core -v."""
import base64
import time
import unittest
from PySide6.QtWidgets import QApplication
from app import AirFrame
from profiles import identify, fit_rect


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = AirFrame(autostart=False)
        self.window.settings = {}

    def tearDown(self): self.window.close()

    def send(self,kind,value):
        self.window.handle_event(kind+' '+base64.b64encode(value.encode()).decode())

    def test_exact_model(self):
        self.assertEqual(identify('iPhone15,2').key,'14pro')
        self.assertEqual(identify('unknown').key,'generic')
        self.assertEqual(identify('iPhone').key,'generic')

    def test_device_switch_resets_identity_and_geometry(self):
        self.send('device','a'); self.send('model','iPhone15,2')
        self.window.handle_event('size 393 852')
        self.assertEqual(self.window.profile.key,'14pro')
        self.send('device','b'); self.send('model','unknown')
        self.assertIsNone(self.window.stream_ratio)
        self.assertEqual(self.window.profile.key,'generic')

    def test_override_per_device(self):
        self.send('device','a')
        self.window.settings['devices']={self.window.device_id:'15pro'}
        self.send('model','iPhone15,2')
        self.assertEqual(self.window.profile.key,'15pro')
        self.send('device','b'); self.send('model','iPhone15,2')
        self.assertEqual(self.window.profile.key,'14pro')

    def test_pause_keeps_window_and_profile(self):
        self.send('device','a');self.send('model','iPhone15,2')
        self.window.handle_event('frame')
        self.window.last_frame = time.monotonic()-10
        self.window.tick()
        self.assertFalse(self.window.live)
        self.assertEqual(self.window.profile.key,'14pro')
        self.assertIn('pausa',self.window.canvas.empty.text())
        self.window.handle_event('frame')
        self.assertTrue(self.window.live)

    def test_geometry_fits_without_stretch(self):
        for ratio in (393/852,852/393,768/1024):
            x,y,w,h = fit_rect(340,720,ratio)
            self.assertGreaterEqual(x,0); self.assertGreaterEqual(y,0)
            self.assertLessEqual(w,340);self.assertLessEqual(h,720)
            self.assertLess(abs(w/h-ratio),.02)

    def test_bad_size_and_bad_event(self):
        self.window.handle_event('size 0 0'); self.window.handle_event('size nope')
        self.window.handle_event('name !!!')
        self.assertIsNone(self.window.stream_ratio)
        self.assertEqual(self.window.device_name,'')

    def test_video_recovery_keeps_bluetooth_and_phone_identity(self):
        self.send('device','phone');self.send('model','iPhone15,2')
        identity = self.window.device_id
        self.window.mouse_controller.enabled = True
        starts = []
        self.window.start_receiver = lambda: starts.append(True)
        self.window.restart_receiver()
        self.assertEqual(starts,[True])
        self.assertTrue(self.window.mouse_controller.enabled)
        self.assertEqual(self.window.device_id,identity)
        self.assertEqual(self.window.profile.key,'14pro')
        self.assertFalse(self.window.live)
        self.assertIn('riavviato',self.window.canvas.empty.text())


if __name__=='__main__': unittest.main()
