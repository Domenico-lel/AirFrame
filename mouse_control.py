"""Qt lifecycle and user setup for the optional BLE mouse worker."""
import json
import os
from pathlib import Path
import sys
import time
from collections import deque

from PySide6.QtCore import QObject, QProcess, QTimer, Signal, Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QDialogButtonBox, QSlider


class MouseController(QObject):
    changed = Signal()
    connected_changed = Signal(bool)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.log = getattr(parent, 'log', lambda line: None)
        self.last_diagnostics = None
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.errorOccurred.connect(self._error)
        self.process.finished.connect(self._finished)
        self.buffer = ''
        self.message = 'Mouse Bluetooth non attivo'
        self.enabled = False
        self.connected = False
        self.starting = False
        self.sequence = 0
        self.pending = {}
        self.input_queue = deque()
        self.input_id = None
        self.wake_ready = False
        self.wake_pending = False
        self.wake_feedback = ''
        self.last_wake = 0.
        self._closing = False
        self._wanted_start = False
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timed_out)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(2000)
        self.status_timer.timeout.connect(self._poll_status)
        self.status_timer.start()

    def _poll_status(self):
        if self.enabled and 'status' not in self.pending.values():
            self.command('status')

    def start(self):
        if self.enabled or self.starting:
            return
        self.log('Bluetooth: avvio richiesto dal PC')
        self._closing = False
        self._wanted_start = True
        self.starting = True
        self.message = 'Preparazione del mouse Bluetooth…'
        self.changed.emit()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.buffer = ''
            if getattr(sys, 'frozen', False):
                program, arguments = str(self.root/'AirFrameMouse.exe'), []
            else:
                program, arguments = sys.executable, ['-u', str(self.root/'bluetooth_mouse.py')]
            self.process.start(program, arguments)
            # Commands may be queued before QProcess has finished starting.
        self.command('start')
        self.timeout.start(20000)

    def command(self, command, **values):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.sequence += 1
        data = dict(id=self.sequence, command=command, **values)
        if command in ('start', 'stop', 'probe', 'wake', 'status'):
            self.pending[self.sequence] = command
        self.process.write((json.dumps(data)+'\n').encode('utf-8'))
        return self.sequence

    def _input(self, command, **values):
        if not self.connected:
            return
        # Coalesce motion while a notification is in flight; never reorder a
        # movement across a button transition. Only one HID command is queued
        # in the subprocess at a time, so Escape cannot trail stale motion.
        if command == 'move' and self.input_queue and self.input_queue[-1][0] == 'move':
            last = self.input_queue[-1][1]
            for axis in ('dx', 'dy'):
                last[axis] = max(-2048, min(2048, last[axis]+values[axis]))
        else:
            self.input_queue.append((command, values))
        if len(self.input_queue) > 64:
            self.stop()
            self.message = 'Il collegamento mouse è troppo lento. Riattivalo per riprovare.'
            self.changed.emit()
            return
        self._drain_input()

    def _drain_input(self):
        if self.connected and self.input_id is None and self.input_queue:
            command, values = self.input_queue.popleft()
            # Send just one HID packet per worker command. Residual motion stays
            # here, where Escape can discard it instead of waiting behind an
            # entire split movement already inside the worker's stdin queue.
            axes = ('dx', 'dy') if command == 'move' else ('delta',) if command == 'wheel' else ()
            if axes:
                part = {axis: max(-127, min(127, values[axis])) for axis in axes}
                remaining = {axis: values[axis]-part[axis] for axis in axes}
                if any(remaining.values()):
                    self.input_queue.appendleft((command, remaining))
                values = part
            self.input_id = self.command(command, **values)

    def move(self, dx, dy):
        if self.connected:
            self._input('move', dx=max(-2048,min(2048,dx)), dy=max(-2048,min(2048,dy)))

    def buttons(self, buttons):
        if self.connected:
            self._input('buttons', buttons=buttons)

    def wheel(self, delta):
        if self.connected:
            self._input('wheel', delta=max(-2048,min(2048,delta)))

    def release(self):
        # An emergency release drops stale movement; normal button-up events
        # retain their preceding button-down so quick clicks are not lost.
        self.input_queue.clear()
        if self.connected:
            self._input('buttons', buttons=0)

    def wake(self):
        """Deliberate Home-button attempt; never depends on a live video stream."""
        if not self.wake_ready or self.wake_pending:
            return
        if time.monotonic() - self.last_wake < 2:
            return
        self.input_queue.clear()
        if self.connected:
            # Preserve release ordering after an in-flight mouse press, without
            # requiring the ordinary mouse channel when iOS is suspended.
            self.command('buttons', buttons=0)
        self.last_wake = time.monotonic()
        self.wake_pending = True
        self.wake_feedback = 'Invio del tasto Home Bluetooth…'
        self.command('wake')
        self.changed.emit()

    def stop(self):
        self.timeout.stop()
        self._wanted_start = False
        self.wake_ready = False
        self.release()
        self.input_queue.clear()
        self._set_connected(False)
        self.enabled = False
        self.starting = False
        self.command('stop')
        self.message = 'Mouse Bluetooth non attivo'
        self.changed.emit()

    def close(self):
        self._closing = True
        self.status_timer.stop()
        self.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.closeWriteChannel()
            if not self.process.waitForFinished(1500):
                self.process.kill()
                self.process.waitForFinished(1000)

    def _set_connected(self, connected):
        if connected != self.connected:
            self.connected = connected
            if not connected:
                self.input_queue.clear()
            self.connected_changed.emit(connected)

    def _read(self):
        self.buffer += bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            try:
                self._event(json.loads(line))
            except (ValueError, TypeError):
                continue
        if len(self.buffer) > 65536:
            self.buffer = ''

    def _event(self, data):
        if data.get('type') == 'response':
            if data.get('id') == self.input_id:
                self.input_id = None
                if not data.get('ok'):
                    # Locking can reject a mouse report already in flight.
                    # Preserve the BLE service so explicit Home/wake still works.
                    self.input_queue.clear()
                    self._set_connected(False)
                    self.command('status')
                    self.message = self._error_text(data.get('error'))
                    self.changed.emit()
                    return
                QTimer.singleShot(0, self._drain_input)
            command = self.pending.pop(data.get('id'), None)
            if command == 'status' and data.get('ok'):
                self._apply_status(data.get('result', {}))
            elif command == 'wake':
                self.wake_pending = False
                self.wake_feedback = ('Tasto Home inviato. Controlla se l’iPhone si è riattivato: la ripresa del video dipende da iOS.'
                                      if data.get('ok') else 'Richiamo non inviato: '+str(data.get('error') or 'collegamento Bluetooth non disponibile')[:250])
                self.changed.emit()
            elif command == 'start':
                self.timeout.stop()
                self.starting = False
                if not self._wanted_start:
                    self.command('stop')
                    return
                self.enabled = bool(data.get('ok'))
                if self.enabled:
                    self._apply_status(data.get('result', {}))
                else:
                    self.message = self._error_text(data.get('error'))
                self.changed.emit()
            elif not data.get('ok') and self.enabled:
                # Input failures must release local mouse capture immediately.
                self._set_connected(False)
                self.message = self._error_text(data.get('error'))
                self.changed.emit()
        elif data.get('type') == 'event':
            event = data.get('event')
            if event == 'status':
                self._apply_status(data)
            elif event in ('error', 'fatal'):
                self._set_connected(False)
                self.wake_ready = False
                self.message = self._error_text(data.get('message') or data.get('error'))
                self.changed.emit()
                self.log('Bluetooth errore: '+self.message)
            elif event == 'diagnostic':
                # The worker emits code locations/counters, never input payloads.
                self.log('Bluetooth diagnostica: '+json.dumps(data,ensure_ascii=True))

    def _apply_status(self, state):
        diagnostic = {key: value for key, value in state.items()
                      if key not in ('peer_id', 'peer_name', 'type', 'event')}
        if diagnostic != self.last_diagnostics:
            self.log('Bluetooth stato: '+json.dumps(diagnostic,ensure_ascii=True))
            self.last_diagnostics = diagnostic
        self.enabled = self._wanted_start and bool(state.get('active'))
        self._set_connected(self.enabled and bool(state.get('ready')))
        self.wake_ready = self.enabled and bool(state.get('wake_ready'))
        messages = {
            'ready': 'Bluetooth collegato · AssistiveTouch deve essere attivo sull’iPhone',
            'link_disconnected': 'iPhone scollegato dal Bluetooth · riconnetti il PC dai dispositivi di AssistiveTouch',
            'stopped': 'Mouse Bluetooth non attivo',
            'suspended': 'L’iPhone ha sospeso gli input Bluetooth',
            'multiple_peers': 'Più dispositivi collegati: scollega gli altri per usare il mouse',
            'unapproved_peer': 'Dispositivo diverso: disattiva e riattiva il mouse per abbinarlo',
            'waiting_for_peer': 'In attesa dell’iPhone · apri Dispositivi Bluetooth in AssistiveTouch',
        }
        self.message = (messages.get(state.get('reason'), 'Preparazione Bluetooth…')
                        if self._wanted_start else messages['stopped'])
        self.changed.emit()

    @staticmethod
    def _error_text(error):
        return 'Mouse non disponibile: ' + str(error or 'controlla il Bluetooth del PC')[:350]

    def _stderr(self):
        detail = bytes(self.process.readAllStandardError()).decode('utf-8', errors='replace').strip()
        if detail:
            # stderr also carries harmless Python warnings. Only structured
            # error/fatal events or process failure may change connection state.
            self.log('Bluetooth stderr: '+detail[-2000:])

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.timeout.stop()
            self.starting = self.enabled = False
            self._set_connected(False)
            self.message = self._error_text('componente AirFrameMouse non avviato')
            self.changed.emit()

    def _finished(self, *_):
        self.timeout.stop()
        self.enabled = self.starting = False
        self._set_connected(False)
        self.pending.clear()
        self.input_queue.clear()
        self.input_id = None
        self.wake_ready = False
        self.wake_pending = False
        if self._wanted_start and not self._closing:
            self.message = 'Componente mouse interrotto. Premi Attiva per riprovare.'
        self.changed.emit()

    def _timed_out(self):
        self.stop()
        self.process.kill()
        self.message = 'Il Bluetooth non risponde. Riattivalo in Windows e riprova.'
        self.changed.emit()


class MouseDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.controller = owner.mouse_controller
        self.setWindowTitle('AirFrame · Controlla iPhone dal PC')
        self.setMinimumWidth(430)
        self.setMaximumWidth(540)
        layout = QVBoxLayout(self)
        title = QLabel('Controlla l’iPhone dal PC')
        title.setStyleSheet('font-size:17px; font-weight:600; padding-bottom:8px;')
        layout.addWidget(title)
        intro = QLabel('I comandi partono dal tuo PC. Non serve un altro mouse o accessorio e non devi installare app sull’iPhone. Collega il PC tramite Bluetooth per provare il controllo e il richiamo.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        pc_name = os.environ.get('COMPUTERNAME', 'questo PC')
        instructions = QLabel(
            '1. Premi «Collega il PC via Bluetooth».\n\n'
            '2. Sull’iPhone apri Impostazioni → Accessibilità → Tocco → AssistiveTouch. Attivalo, poi apri Dispositivi → Dispositivi Bluetooth.\n\n'
            f'3. Seleziona «{pc_name}»: è il computer. Se Windows mostra «Aggiungi un dispositivo», apri la notifica e completa l’abbinamento anche sul PC.\n\n'
            '4. Quando compare «Bluetooth collegato», controlla che AssistiveTouch sia ancora attivo, avvia Duplica schermo e premi «Usa mouse». Il richiamo si prova anche con video in pausa.')
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.state = QLabel()
        self.state.setWordWrap(True)
        self.state.setStyleSheet('background:#303641; border-radius:6px; padding:10px;')
        layout.addWidget(self.state)
        self.speed_label = QLabel()
        layout.addWidget(self.speed_label)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(25, 300)
        self.speed_slider.setValue(round(owner.mouse_overlay.sensitivity*100))
        self.speed_slider.setAccessibleName('Velocità puntatore')
        self.speed_slider.setToolTip('Alza se il puntatore si muove poco; abbassa se supera il bersaglio. Maiusc rallenta temporaneamente per movimenti fini.')
        self.speed_slider.valueChanged.connect(self._speed_changed)
        self.speed_label.setText(f'Velocità puntatore: {self.speed_slider.value()}% · Maiusc per precisione')
        layout.addWidget(self.speed_slider)
        self.start_button = QPushButton('Collega il PC via Bluetooth')
        self.start_button.clicked.connect(self.controller.start)
        layout.addWidget(self.start_button)
        self.capture_button = QPushButton('Usa mouse')
        self.capture_button.clicked.connect(self._capture)
        layout.addWidget(self.capture_button)
        self.wake_button = QPushButton('Prova richiamo · tasto Home')
        self.wake_button.setToolTip('Invia un tasto Home Bluetooth anche se il video è in pausa. Effetto da verificare sull’iPhone.')
        self.wake_button.clicked.connect(self._wake)
        layout.addWidget(self.wake_button)
        self.wake_status = QLabel()
        self.wake_status.setWordWrap(True)
        layout.addWidget(self.wake_status)
        self.video_reset_button = QPushButton('Ripristina video AirPlay')
        self.video_reset_button.setToolTip('Riavvia solo il ricevitore video. Poi seleziona di nuovo AirFrame in Duplica schermo sull’iPhone.')
        self.video_reset_button.clicked.connect(owner.restart_receiver)
        layout.addWidget(self.video_reset_button)
        self.stop_button = QPushButton('Disattiva controllo Bluetooth')
        self.stop_button.clicked.connect(self.controller.stop)
        layout.addWidget(self.stop_button)
        note = QLabel('Clicca e trascina per scorrere; Esc restituisce il mouse al PC.\n\nIl richiamo invia il tasto Home: se il telefono è già attivo, può tornare alla Home. Face ID o il codice restano necessari quando richiesti da iOS. Non riavvia automaticamente Duplica schermo.\n\nSe il richiamo resta disabilitato dopo un vecchio abbinamento, dissocia il PC dall’iPhone e abbinalo di nuovo per aggiornare il profilo Bluetooth.')
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('Chiudi')
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.controller.changed.connect(self.refresh)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(500)
        self.finished.connect(self._finished)
        self.refresh()

    def refresh(self):
        c = self.controller
        self.state.setText(c.message)
        self.start_button.setEnabled(not c.enabled and not c.starting)
        self.stop_button.setEnabled(c.enabled or c.starting)
        self.capture_button.setEnabled(c.connected and self.owner.live)
        self.capture_button.setText('Usa mouse' if self.owner.live else 'Avvia Duplica schermo per usare il mouse')
        self.wake_button.setEnabled(c.wake_ready and not c.wake_pending and time.monotonic()-c.last_wake >= 2)
        self.wake_status.setText(c.wake_feedback or ('Richiamo disponibile anche con video in pausa.' if c.wake_ready else 'Richiamo in attesa del collegamento Bluetooth.'))

    def _wake(self):
        self.owner.mouse_overlay.release_capture('wake request')
        self.controller.wake()

    def _speed_changed(self, value):
        self.speed_label.setText(f'Velocità puntatore: {value}% · Maiusc per precisione')
        self.owner.set_mouse_sensitivity(value/100)

    def _capture(self):
        self.accept()
        QTimer.singleShot(150, self.owner.capture_mouse)

    def _finished(self, *_):
        self.refresh_timer.stop()
        self.controller.changed.disconnect(self.refresh)
