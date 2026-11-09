"""AirFrame Windows prototype. GPL-3.0-or-later. No iPhone companion required."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRegion, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
    QHBoxLayout, QPushButton, QDialog, QComboBox, QCheckBox, QLineEdit,
    QFormLayout, QDialogButtonBox, QMessageBox)

from profiles import PROFILES, identify, fit_rect
from native_video import NativeVideo
from mouse_control import MouseController, MouseDialog
from mouse_overlay import MouseOverlay

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
DATA = Path(os.environ.get('LOCALAPPDATA', str(ROOT))) / 'AirFrame'
DATA.mkdir(parents=True, exist_ok=True)
SETTINGS_PATH = DATA / 'settings.json'


def load_settings():
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class IconButton(QPushButton):
    def __init__(self, kind, tip, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(30, 30)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse() or self.hasFocus():
            p.setBrush(QColor('#424650'))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(1, 1, 28, 28), 7, 7)
        p.setPen(QPen(QColor('#f0f1f4'), 1.5))
        if self.kind == 'close':
            p.drawLine(11, 11, 19, 19); p.drawLine(11, 19, 19, 11)
        elif self.kind == 'min':
            p.drawLine(10, 15, 20, 15)
        elif self.kind == 'settings':
            for y, x in [(10, 13), (15, 19), (20, 12)]:
                p.drawLine(8, y, 22, y)
                p.setBrush(QColor('#282c35')); p.drawEllipse(QPointF(x, y), 2, 2)
        elif self.kind == 'expand':
            p.drawRect(9, 9, 12, 12)
        elif self.kind == 'pin':
            p.drawLine(11, 9, 19, 9); p.drawLine(13, 9, 13, 15)
            p.drawLine(17, 9, 17, 15); p.drawLine(10, 15, 20, 15)
            p.drawLine(15, 15, 15, 23)
        elif self.kind == 'mouse':
            p.drawRoundedRect(QRectF(9, 6, 12, 18), 6, 6)
            p.drawLine(15, 7, 15, 13)


class Toolbar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        self.window().toggle_size()


class PhoneCanvas(QWidget):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.video = QWidget(self)
        self.video.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.video.setStyleSheet('background: #101319;')
        self.video.setAccessibleName('Schermo duplicato del dispositivo')
        self.empty = QLabel(self.video)
        self.empty.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet('color:#f2f3f5; background:#101319; padding:22px; font-size:14px;')
        self.island = QWidget(self.video)
        self.island.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.island.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.island.setStyleSheet('background:#020305; border-radius:13px;')
        self.screen = QRectF()

    def resizeEvent(self, event):
        self.layout_phone()

    def layout_phone(self):
        profile = self.owner.profile
        ratio = self.owner.stream_ratio or profile.width / profile.height
        aw, ah = max(30, self.width()-28), max(30, self.height()-28)
        x, y, w, h = fit_rect(aw, ah, ratio)
        x += 14; y += 14
        self.screen = QRectF(x, y, w, h)
        self.video.setGeometry(x, y, w, h)
        r = min(w, h) * profile.radius if self.owner.settings.get('frame', True) else 0
        clip = QPainterPath(); clip.addRoundedRect(QRectF(0, 0, w, h), r, r)
        self.video.setMask(QRegion(clip.toFillPolygon().toPolygon()))
        self.empty.setGeometry(0, 0, w, h)
        show_cutout = (self.owner.settings.get('island', True)
                       and self.owner.settings.get('frame', True)
                       and profile.cutout in ('island', 'notch') and ratio < 1)
        iw = int(w * (.32 if profile.cutout == 'island' else .48))
        ih = max(12, int(w * .078))
        self.island.setGeometry((w-iw)//2, max(4, int(w*.025)), iw, ih)
        island_clip = QPainterPath()
        island_clip.addRoundedRect(QRectF(0,0,iw,ih),ih/2,ih/2)
        self.island.setMask(QRegion(island_clip.toFillPolygon().toPolygon()))
        self.island.setVisible(show_cutout)
        self.island.raise_()
        self.update()

    def paintEvent(self, event):
        if not self.owner.settings.get('frame', True):
            return
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = min(self.screen.width(), self.screen.height()) * self.owner.profile.radius
        outer = self.screen.adjusted(-7, -7, 7, 7)
        p.setBrush(QColor('#17191e')); p.setPen(QPen(QColor('#737982'), 2))
        p.drawRoundedRect(outer, r+7, r+7)
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor('#30343c'), 3))
        p.drawRoundedRect(self.screen.adjusted(-3,-3,3,3), r+3, r+3)
        p.setPen(QPen(QColor('#8b9097'), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        x, y, w, h = outer.x(), outer.y(), outer.width(), outer.height()
        if h > w:
            p.drawLine(QPointF(x-2, y+h*.19), QPointF(x-2, y+h*.23))
            p.drawLine(QPointF(x-2, y+h*.27), QPointF(x-2, y+h*.33))
            p.drawLine(QPointF(x+w+2, y+h*.24), QPointF(x+w+2, y+h*.34))


class SettingsDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.setWindowTitle('AirFrame · Impostazioni')
        self.setMinimumWidth(410)
        layout = QVBoxLayout(self)
        intro = QLabel('La cornice segue il modello comunicato dal telefono.\nSe manca, puoi scegliere un profilo e memorizzarlo.')
        intro.setWordWrap(True); layout.addWidget(intro)
        form = QFormLayout()
        self.name = QLineEdit(owner.settings.get('name', 'AirFrame'))
        self.name.setMaxLength(48); form.addRow('Nome in Duplica schermo', self.name)
        self.profile = QComboBox()
        self.profile.addItem('Riconosci automaticamente', 'auto')
        for key, p in PROFILES.items():
            self.profile.addItem(p.label, key)
        key = owner.override_key()
        index = self.profile.findData(key)
        self.profile.setCurrentIndex(max(0,index)); form.addRow('Cornice', self.profile)
        self.frame = QCheckBox('Mostra la scocca'); self.frame.setChecked(owner.settings.get('frame',True))
        self.island = QCheckBox('Mostra Island / notch decorativo')
        self.island.setChecked(owner.settings.get('island',True))
        form.addRow(self.frame); form.addRow(self.island)
        layout.addLayout(form)
        note = QLabel('Disattiva Island / notch se sono già presenti nel video.\nLa decorazione è statica; non riproduce le attività di iOS.\n\nAndroid: ricezione non ancora implementata.\nBlocco schermo: la ripresa dipende anche da iOS.')
        note.setWordWrap(True); layout.addWidget(note)
        network = QPushButton('Configura accesso alla rete locale…')
        network.clicked.connect(owner.configure_firewall); layout.addWidget(network)
        logs = QPushButton('Apri cartella diagnostica'); logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA))))
        layout.addWidget(logs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)


class AirFrame(QWidget):
    def __init__(self, autostart=True):
        super().__init__()
        self.settings = load_settings()
        self.profile = PROFILES['14pro']
        self.stream_ratio = None
        self.device_id = ''; self.device_model = ''; self.device_name = ''
        self.last_frame = 0.; self.live = False; self.buffer = ''
        self.manual_stop = False; self.failures = 0; self.receiver_ready = False
        self.setWindowTitle('AirFrame — Duplica schermo')
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(408, 860); self.setMinimumSize(330, 510)
        root = QVBoxLayout(self); root.setContentsMargins(12,8,12,8); root.setSpacing(2)
        self.toolbar = Toolbar(self); self.toolbar.setFixedHeight(48)
        self.toolbar.setObjectName('toolbar')
        bar = QHBoxLayout(self.toolbar); bar.setContentsMargins(8,4,6,4); bar.setSpacing(2)
        for kind, tip, fn in [('close','Chiudi AirFrame',self.close), ('min','Riduci a icona',self.showMinimized)]:
            b = IconButton(kind,tip); b.clicked.connect(fn); bar.addWidget(b)
        texts = QVBoxLayout(); texts.setSpacing(0)
        self.title = QLabel('AirFrame'); self.title.setObjectName('deviceTitle')
        self.title.setMaximumWidth(170)
        self.subtitle = QLabel('Preparazione ricevitore…'); self.subtitle.setObjectName('subtitle')
        texts.addWidget(self.title); texts.addWidget(self.subtitle); bar.addLayout(texts,1)
        for kind, tip, fn in [('mouse','Controllo mouse Bluetooth',self.open_mouse),('pin','Sempre in primo piano',self.toggle_pin),('expand','Cambia dimensione',self.toggle_size),('settings','Impostazioni',self.open_settings)]:
            b = IconButton(kind,tip); b.clicked.connect(fn); bar.addWidget(b)
        root.addWidget(self.toolbar)
        self.canvas = PhoneCanvas(self); root.addWidget(self.canvas,1)
        self.status = QLabel('Nessuna app da installare su iPhone',self)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setObjectName('status'); root.addWidget(self.status)
        self.setStyleSheet('''
            QWidget {font-family:"Segoe UI"; font-size:12px; color:#eff1f5;}
            QWidget#toolbar {background:#292d36; border-radius:10px;}
            QLabel#deviceTitle {font-size:12px; font-weight:600;}
            QLabel#subtitle {font-size:10px; color:#c0c8d4;}
            QLabel#status {font-size:11px; color:#d2d8e2; padding:3px; background:#252a33; border-radius:6px;}
            QDialog {background:#20242c;}
            QLineEdit, QComboBox {background:#303641; padding:7px; border:1px solid #626c7b; border-radius:5px;}
            QPushButton {padding:7px; background:#363d49; border:1px solid #697485; border-radius:5px;}
            QPushButton:hover {background:#454f5e;} QPushButton:focus {border:2px solid #93baff;}
            QPushButton:disabled {color:#8a929e; background:#282d35; border-color:#414854;}
            QComboBox QAbstractItemView {background:#303641; color:#ffffff; selection-background-color:#4a6081;}
        ''')
        self.mouse_controller = MouseController(ROOT, self)
        self.mouse_overlay = MouseOverlay(self.canvas.video)
        try:
            self.mouse_overlay.set_sensitivity(self.settings.get('mouse_sensitivity', 1.0))
        except (TypeError, ValueError):
            self.mouse_overlay.set_sensitivity(1.0)
        self.mouse_overlay.movement.connect(self.mouse_controller.move)
        self.mouse_overlay.buttons.connect(self.mouse_controller.buttons)
        self.mouse_overlay.wheel.connect(self.mouse_controller.wheel)
        self.mouse_overlay.capture_changed.connect(self.mouse_capture_changed)
        self.mouse_overlay.capture_lost.connect(lambda reason: self.log('Mouse: cattura terminata ('+reason+')'))
        self.mouse_controller.connected_changed.connect(self.mouse_connection_changed)
        self.receiver = QProcess(self)
        self.receiver.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.receiver.readyReadStandardOutput.connect(self.read_output)
        self.receiver.finished.connect(self.receiver_finished)
        self.receiver.errorOccurred.connect(self.receiver_error)
        self.native_video = NativeVideo(self.canvas.video, lambda:int(self.receiver.processId()), self.log)
        self.video_timer = QTimer(self)
        self.video_timer.timeout.connect(self.refresh_video); self.video_timer.start(150)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(1000)
        self.idle_message()
        self.resolve_profile()
        if autostart: QTimer.singleShot(350, self.start_receiver)
        else: self.subtitle.setText('Anteprima · non collegato')

    def refresh_video(self):
        self.native_video.update()
        self.native_video.overlay(self.canvas.island)
        if self.canvas.empty.isVisible():
            self.native_video.overlay(self.canvas.empty)
            self.native_video.overlay(self.canvas.island)
        self.mouse_overlay.restack()

    def open_mouse(self):
        self.mouse_overlay.release_capture('setup')
        dialog = MouseDialog(self)
        dialog.exec()
        dialog.deleteLater()

    def capture_mouse(self):
        self.mouse_overlay.set_connected(self.mouse_controller.connected and self.live)
        if not self.mouse_overlay.start_capture():
            self.log('Mouse: cattura non avviata (Bluetooth='+str(self.mouse_controller.connected)+', video='+str(self.live)+')')
            self.status.setText('Mouse non pronto · verifica Bluetooth e video')

    def set_mouse_sensitivity(self, value):
        self.mouse_overlay.set_sensitivity(value)
        self.settings['mouse_sensitivity'] = self.mouse_overlay.sensitivity
        try:
            temp = SETTINGS_PATH.with_suffix('.tmp')
            temp.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
            temp.replace(SETTINGS_PATH)
        except OSError as exc:
            self.log('Mouse: salvataggio velocità non riuscito ('+type(exc).__name__+')')

    def restart_receiver(self):
        """Recover the video process without changing BLE pairing or the frame."""
        self.log('AirFrame: ripristino video richiesto')
        self.live = False
        self.last_frame = 0.
        self.mouse_overlay.set_connected(False)
        self.manual_stop = True
        if self.receiver.state() != QProcess.ProcessState.NotRunning:
            self.receiver.kill()
            self.receiver.waitForFinished(2000)
        self.native_video.hwnd = 0
        self.buffer = ''
        self.failures = 0
        self.start_receiver()
        self.idle_message('Ricevitore video riavviato\n\nSull’iPhone apri Duplica schermo\ne seleziona di nuovo AirFrame.\n\nIl collegamento Bluetooth è mantenuto.')

    def mouse_connection_changed(self, connected):
        self.mouse_overlay.set_connected(connected and self.live)

    def mouse_capture_changed(self, active):
        self.log('Mouse: cattura '+('attiva' if active else 'rilasciata')+
                 ('; input='+('raw' if self.mouse_overlay.raw_input.active else 'Qt')+
                  '; sensibilita='+str(self.mouse_overlay.sensitivity) if active else ''))
        if active:
            self.status.setText('Mouse sull’iPhone · Esc per tornare al PC')
        else:
            self.mouse_controller.release()
            if self.live:
                self.status.setText('Schermo in diretta · usa il tuo iPhone')

    def idle_message(self, text=None):
        name = self.settings.get('name','AirFrame')
        self.canvas.empty.setText(text or f'Il tuo iPhone, qui.\n\nCollega iPhone e PC alla stessa rete.\n\nApri Centro di Controllo\n→ Duplica schermo\n→ {name}\n\nNessuna app sull’iPhone.')
        self.canvas.empty.show(); self.canvas.island.raise_()

    def override_key(self):
        return self.settings.get('devices',{}).get(self.device_id,'auto') if self.device_id else self.settings.get('preview','auto')

    def resolve_profile(self):
        key = self.override_key()
        self.profile = PROFILES[key] if key in PROFILES else identify(self.device_model)
        if not self.device_model and key == 'auto': self.profile = PROFILES['14pro']
        self.canvas.layout_phone()
        self.title.setText(self.device_name or 'AirFrame')
        self.title.setToolTip(self.device_name or 'AirFrame')

    def start_receiver(self):
        if self.receiver.state() != QProcess.ProcessState.NotRunning: return
        self.manual_stop = False; self.receiver_ready = False
        exe = ROOT / 'engine' / 'uxplay.exe'
        if not exe.exists():
            self.idle_message('Ricevitore non trovato.\n\nMantieni la cartella engine accanto ad AirFrame.exe.')
            self.subtitle.setText('Installazione incompleta'); return
        env = QProcessEnvironment.systemEnvironment()
        env.insert('PATH', str(exe.parent) + os.pathsep + env.value('PATH'))
        # This enables metadata events only. The native video window is reparented
        # after creation, so the renderer never subclasses another process's HWND.
        env.insert('AIRFRAME_WINDOW', 'events')
        env.insert('GST_PLUGIN_PATH', str(ROOT/'engine'/'plugins'))
        env.insert('GST_PLUGIN_SYSTEM_PATH', str(ROOT/'engine'/'plugins'))
        env.insert('GST_PLUGIN_SCANNER', str(ROOT/'engine'/'gst-plugin-scanner.exe'))
        env.insert('GST_REGISTRY', str(DATA/'gst-registry.bin'))
        self.receiver.setProcessEnvironment(env)
        self.receiver.setWorkingDirectory(str(DATA))
        config = DATA/'receiver.conf'; config.write_text('',encoding='utf-8')
        register = DATA/'paired-devices.txt'
        args = ['-rc',str(config),'-n',self.settings.get('name','AirFrame'),'-nh',
                '-vs','d3d11videosink','-as','wasapisink','-avdec',
                '-nc','no','-nofreeze','-reset','45','-p','7100','-pin','-reg',str(register),
                '-key',str(DATA/'receiver.pem'),'-s','1920x1080']
        self.receiver.start(str(exe), args)
        self.subtitle.setText('Avvio AirPlay…')

    def log(self, line):
        path = DATA/'receiver.log'
        try:
            if path.exists() and path.stat().st_size > 2_000_000:
                path.replace(DATA/'receiver.previous.log')
            with path.open('a',encoding='utf-8') as f:
                f.write(time.strftime('%H:%M:%S ') + line + '\n')
        except OSError: pass

    def read_output(self):
        self.buffer += bytes(self.receiver.readAllStandardOutput()).decode('utf-8',errors='replace')
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n',1)
            line = line.rstrip('\r')
            if line.startswith('@AF '): self.handle_event(line[4:])
            else: self.log(line)
        if len(self.buffer) > 100_000: self.buffer = self.buffer[-5000:]

    def handle_event(self, event):
        kind, _, value = event.partition(' ')
        if kind not in ('frame',): self.log('AirFrame event: '+event)
        if kind == 'frame':
            self.last_frame = time.monotonic(); self.failures = 0
            if not self.live:
                self.live = True; self.canvas.empty.hide(); self.canvas.island.raise_()
                self.mouse_connection_changed(self.mouse_controller.connected)
            self.status.setText('Mouse sull’iPhone · Esc per tornare al PC' if self.mouse_overlay.active else 'Schermo in diretta · usa il tuo iPhone')
            self.subtitle.setText(self.profile.label if self.profile.key != 'generic' else 'Modello non comunicato')
        elif kind == 'size':
            try:
                w,h = map(int,value.split())
                if w > 0 and h > 0:
                    old_landscape = bool(self.stream_ratio and self.stream_ratio > 1)
                    self.stream_ratio = w/h
                    if old_landscape != (w>h):
                        self.resize(860,500) if w>h else self.resize(408,860)
                    self.canvas.layout_phone()
            except ValueError: pass
        else:
            try: text = base64.b64decode(value,validate=True).decode('utf-8',errors='replace')
            except (ValueError,UnicodeError): return
            if kind == 'ready':
                self.receiver_ready = True
                self.subtitle.setText('Pronto · Duplica schermo')
                self.status.setText('In attesa · iPhone e PC sulla stessa rete')
            elif kind == 'device':
                new_id = hashlib.sha256(text.encode()).hexdigest()[:24] if text else ''
                if new_id != self.device_id:
                    self.stream_ratio = None; self.device_model = ''; self.device_name = ''
                    # AirPlay and BLE identities are unrelated. A changed video
                    # source must never silently keep controlling the old phone.
                    self.mouse_overlay.release_capture('video device changed')
                    if self.device_id:
                        self.mouse_controller.stop()
                self.device_id = new_id
                self.resolve_profile()
            elif kind == 'model':
                self.device_model = text; self.resolve_profile()
            elif kind == 'name':
                self.device_name = text; self.resolve_profile()
            elif kind == 'pin':
                self.idle_message(f'Conferma la connessione\n\nInserisci questo codice sull’iPhone:\n\n{text}\n\nIl codice autorizza questo dispositivo.')
                self.subtitle.setText('Abbinamento in corso')

    def tick(self):
        if self.live and time.monotonic()-self.last_frame > 8:
            self.live = False
            self.mouse_overlay.set_connected(False)
            self.idle_message('Trasmissione in pausa\n\nPer tentare il richiamo dal PC:\nbarra → mouse → Prova richiamo.\nServe il collegamento Bluetooth.\n\nSe iOS ha chiuso la sessione,\nseleziona di nuovo AirFrame\nin Duplica schermo sull’iPhone.\n\nIl ricevitore resta disponibile.')
            self.subtitle.setText('In attesa di nuovi fotogrammi')
            self.status.setText('Pausa · finestra e cornice mantenute')

    def receiver_finished(self, code, status):
        self.receiver_ready = False; self.live = False
        self.mouse_overlay.set_connected(False)
        if self.manual_stop: return
        self.failures += 1
        self.subtitle.setText('Ricevitore interrotto')
        if self.failures <= 3:
            self.status.setText('Riavvio del ricevitore…')
            QTimer.singleShot(2000,self.start_receiver)
        else:
            self.idle_message('Impossibile avviare il ricevitore.\n\nApri Impostazioni → cartella diagnostica\nper leggere receiver.log.\n\nChiudi e riapri AirFrame dopo la correzione.')
            self.status.setText('Errore · consulta la diagnostica')

    def receiver_error(self,error):
        if self.manual_stop: return
        self.log(self.receiver.errorString())
        if error == QProcess.ProcessError.FailedToStart:
            self.idle_message('Avvio non riuscito.\n\nVerifica che engine e le sue DLL siano presenti.\nConsulta receiver.log nelle impostazioni.')
            self.subtitle.setText('Errore di avvio')

    def open_settings(self):
        d = SettingsDialog(self)
        if d.exec() != QDialog.DialogCode.Accepted: return
        name = d.name.text().strip() or 'AirFrame'
        restart = name != self.settings.get('name','AirFrame')
        self.settings.update(name=name,frame=d.frame.isChecked(),island=d.island.isChecked())
        key = d.profile.currentData()
        if self.device_id:
            self.settings.setdefault('devices',{})[self.device_id] = key
        else: self.settings['preview'] = key
        temp = SETTINGS_PATH.with_suffix('.tmp')
        temp.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8'); temp.replace(SETTINGS_PATH)
        self.resolve_profile()
        if restart:
            self.manual_stop = True; self.receiver.kill(); self.receiver.waitForFinished(2000)
            self.failures = 0; self.start_receiver()
        if not self.live: self.idle_message()

    def configure_firewall(self):
        script = ROOT/'Configura-rete.ps1'
        if script.exists():
            # UAC only after the user explicitly presses the setup button.
            import ctypes
            result = ctypes.windll.shell32.ShellExecuteW(None,'runas','powershell.exe',
                f'-NoProfile -ExecutionPolicy Bypass -File "{script}"',str(ROOT),0)
            if result <= 32: QMessageBox.information(self,'Rete locale','Configurazione non eseguita. Puoi riprovare dalle impostazioni.')

    def toggle_pin(self):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, not bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)); self.show()

    def toggle_size(self):
        landscape = bool(self.stream_ratio and self.stream_ratio > 1)
        if landscape: self.resize(1080,650) if self.width()<1000 else self.resize(860,500)
        else: self.resize(490,1020) if self.height()<950 else self.resize(408,860)

    def closeEvent(self,event):
        self.manual_stop = True
        self.mouse_overlay.release_capture('window closed')
        self.mouse_controller.close()
        self.receiver.kill(); self.receiver.waitForFinished(2000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('AirFrame'); app.setOrganizationName('AirFrame')
    window = AirFrame(autostart='--preview' not in sys.argv)
    window.show()
    if '--mouse-setup' in sys.argv:
        QTimer.singleShot(500, window.open_mouse)
    if '--screenshot' in sys.argv:
        target = sys.argv[sys.argv.index('--screenshot')+1]
        QTimer.singleShot(1300,lambda: (window.grab().save(target),window.close(),app.quit()))
    sys.exit(app.exec())


if __name__ == '__main__': main()
