"""Experimental Windows BLE HID mouse; JSON-lines subprocess, no Qt imports.

Start with Python or freeze this file as a separate console executable. Merely
importing/running/probing never advertises: the explicit ``start`` command does.
Commands have an optional ``id`` and a ``command`` string. Responses are
{type: response, id, ok, result/error}; events are {type: event, event, ...}.

probe, start [expected_peer], stop, status, move (dx,dy), buttons (buttons 0..7),
wheel (delta), release, wake, quit. Deltas are relative HID units, not pixels.
An input acknowledgement means a BLE notification succeeded, not that iOS
performed the intended gesture. ``wake`` sends the documented Apple Home
consumer control, experimentally allowing an already bonded host to wake.
It never asserts that the display woke, unlocked, or restarted AirPlay.

Primary API references:
https://learn.microsoft.com/en-us/windows/apps/develop/devices-sensors/gatt-server
https://github.com/microsoft/BluetoothLEExplorer/blob/master/BluetoothLEExplorer/BluetoothLEExplorer/Models/VirtualKeyboard.cs
https://pywinrt.readthedocs.io/en/latest/types/
https://developer.apple.com/accessories/Accessory-Design-Guidelines.pdf
"""

from __future__ import annotations

import asyncio
import json
import platform
import struct
import sys
import threading
import traceback
import uuid


# Three buttons and signed relative X/Y/wheel; report ID 1 is carried by the
# Report Reference descriptor, not prefixed to the GATT Report payload.
MOUSE_REPORT_MAP = bytes.fromhex(
    "05 01 09 02 A1 01 85 01 09 01 A1 00 "
    "05 09 19 01 29 03 15 00 25 01 95 03 75 01 81 02 "
    "95 01 75 05 81 03 "
    "05 01 09 30 09 31 09 38 15 81 25 7F 75 08 95 03 81 06 "
    "C0 C0"
)
CONSUMER_REPORT_MAP = bytes.fromhex(
    # Consumer Control / Report ID 2 / one 16-bit array usage: 0 release or
    # 0x0040 Menu, mapped by Apple to Home Button (keyboard table 14-3).
    "05 0C 09 01 A1 01 85 02 15 00 26 40 00 "
    "19 00 2A 40 00 75 10 95 01 81 00 C0"
)
REPORT_MAP = MOUSE_REPORT_MAP + CONSUMER_REPORT_MAP
HID_INFORMATION = b"\x11\x01\x00\x03"  # HID 1.11; RemoteWake + NormallyConnectable.
HOME_PRESS = struct.pack('<H', 0x0040)
HOME_RELEASE = b"\x00\x00"
MAX_DELTA = 2048
COMMAND_TIMEOUT = 20
MOUSE_NOTIFY_MIN_INTERVAL = 1 / 60
MOUSE_NOTIFY_FALLBACK_INTERVAL = .030


def short_uuid(value: int) -> uuid.UUID:
    return uuid.UUID(f"0000{value:04x}-0000-1000-8000-00805f9b34fb")


def require_int(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} deve essere un intero tra {low} e {high}.")
    return value


def mouse_reports(buttons: int, dx=0, dy=0, wheel=0):
    """Split large relative motion without dropping any displacement."""
    require_int(buttons, "buttons", 0, 7)
    for name, value in (("dx", dx), ("dy", dy), ("wheel", wheel)):
        require_int(value, name, -MAX_DELTA, MAX_DELTA)
    while True:
        x, y, w = (max(-127, min(127, v)) for v in (dx, dy, wheel))
        yield struct.pack("Bbbb", buttons, x, y, w)
        dx, dy, wheel = dx - x, dy - y, wheel - w
        if dx == dy == wheel == 0:
            return


def enum_name(value):
    return getattr(value, "name", str(value)).lower()


def emit(message):
    print(json.dumps(message, ensure_ascii=True, separators=(",", ":")), flush=True)


class MouseWorker:
    def __init__(self):
        # Keep WinRT loading in this dedicated non-UI process (MTA apartment).
        from winrt.windows.devices.bluetooth import BluetoothAdapter, BluetoothError, BluetoothLEDevice
        from winrt.windows.devices.bluetooth import genericattributeprofile as gatt
        from winrt.windows.storage.streams import DataWriter

        self.Adapter, self.BluetoothError, self.Device = BluetoothAdapter, BluetoothError, BluetoothLEDevice
        self.gatt, self.DataWriter = gatt, DataWriter
        self.loop = asyncio.get_running_loop()
        self.provider = self.report = self.consumer_report = None
        self.consumer_target = None
        self.providers = []
        self.handlers = []
        self.callback_tasks = set()
        self.active = False
        self.starting = False
        self.suspended = False
        self.buttons = 0
        self.peer_id = None
        self.peer_name = None
        self.peer_device = None
        self.peer_device_handler = None
        self.peer_lookup = None
        self.link_connected = None
        self.last_mouse_notify = None
        self.mouse_notify_lock = asyncio.Lock()
        self.expected_peer = None
        self.last_status = None
        self.generation = 0
        self.stopping = False
        self.advertisement_errors = {}
        self.published = set()
        self.diagnostics = self._new_diagnostics()

    @staticmethod
    def _new_diagnostics():
        return {"mouse_report_reads": 0, "consumer_report_reads": 0,
                "control_point_writes": 0, "mouse_notify_attempted": 0,
                "mouse_notify_accepted": 0, "mouse_notify_failed": 0,
                "mouse_nonzero_reports_attempted": 0,
                "mouse_move_commands": 0, "mouse_button_commands": 0,
                "mouse_notify_interval_ms": MOUSE_NOTIFY_FALLBACK_INTERVAL * 1000,
                "mouse_connection_interval_ms": None,
                "mouse_last_failure": None, "callback_errors": 0}

    def _metrics(self):
        # Lazy initialization also supports the isolated no-WinRT test doubles.
        if not hasattr(self, "diagnostics"):
            self.diagnostics = self._new_diagnostics()
        return self.diagnostics

    def _diagnostic_error(self, operation, exc, reason=None):
        # Traceback frames identify the failing code without recording input
        # payloads, device names/IDs, or arbitrary exception-message contents.
        details = {"operation": operation, "exception_type": type(exc).__name__,
                   "traceback": "".join(traceback.format_tb(exc.__traceback__, limit=8))[-6000:]}
        hresult = getattr(exc, "hresult", None)
        if isinstance(hresult, int):
            details["hresult"] = hresult
        if reason is not None:
            details["reason"] = reason
        emit({"type": "event", "event": "diagnostic", **details})

    def buffer(self, value):
        writer = self.DataWriter()
        try:
            writer.write_bytes(value)
            return writer.detach_buffer()
        finally:
            writer.close()

    def _schedule(self, coroutine_factory, *args):
        def schedule():
            task = self.loop.create_task(coroutine_factory(*args))
            self.callback_tasks.add(task)
            task.add_done_callback(self._callback_done)
        try:
            self.loop.call_soon_threadsafe(schedule)
        except RuntimeError:
            pass  # Event loop already closed while Windows releases a handler.

    def _callback_done(self, task):
        self.callback_tasks.discard(task)
        if not task.cancelled() and task.exception():
            exc = task.exception()
            self._metrics()["callback_errors"] += 1
            self._diagnostic_error("callback", exc)
            emit({"type": "event", "event": "error", "error": str(exc)})

    def _listen(self, obj, event, callback):
        token = getattr(obj, f"add_{event}")(callback)
        self.handlers.append((obj, event, token, callback))

    async def _new_provider(self, service):
        result = await self.gatt.GattServiceProvider.create_async(short_uuid(service))
        if result.error != self.BluetoothError.SUCCESS:
            raise RuntimeError(f"Servizio GATT {service:04X}: {enum_name(result.error)}")
        self.providers.append(result.service_provider)
        return result.service_provider

    async def _characteristic(self, provider, characteristic, properties, static=None, encrypted=True):
        parameters = self.gatt.GattLocalCharacteristicParameters()
        parameters.characteristic_properties = properties
        security = self.gatt.GattProtectionLevel.ENCRYPTION_REQUIRED if encrypted else self.gatt.GattProtectionLevel.PLAIN
        parameters.read_protection_level = security
        parameters.write_protection_level = security
        if static is not None:
            parameters.static_value = self.buffer(static)
        result = await provider.service.create_characteristic_async(short_uuid(characteristic), parameters)
        if result.error != self.BluetoothError.SUCCESS:
            raise RuntimeError(f"Caratteristica GATT {characteristic:04X}: {enum_name(result.error)}")
        return result.characteristic

    async def _build(self):
        if self.provider is not None:
            return
        g = self.gatt
        try:
            provider = await self._new_provider(0x1812)
            report = await self._characteristic(provider, 0x2A4D, g.GattCharacteristicProperties.READ | g.GattCharacteristicProperties.NOTIFY)
            consumer = await self._characteristic(provider, 0x2A4D, g.GattCharacteristicProperties.READ | g.GattCharacteristicProperties.NOTIFY)
            for characteristic, report_id in ((report, 1), (consumer, 2)):
                reference = g.GattLocalDescriptorParameters()
                reference.read_protection_level = g.GattProtectionLevel.ENCRYPTION_REQUIRED
                reference.static_value = self.buffer(bytes((report_id, 1)))
                descriptor = await characteristic.create_descriptor_async(short_uuid(0x2908), reference)
                if descriptor.error != self.BluetoothError.SUCCESS:
                    raise RuntimeError(f"Descrittore HID {report_id}: {enum_name(descriptor.error)}")
            # Windows generates the notification CCCD. Do not create 0x2902.
            await self._characteristic(provider, 0x2A4B, g.GattCharacteristicProperties.READ, REPORT_MAP)
            # The RemoteWake capability makes the host eligible to consider
            # this HID device for wake. It does not guarantee iOS behavior.
            await self._characteristic(provider, 0x2A4A, g.GattCharacteristicProperties.READ, HID_INFORMATION)
            control = await self._characteristic(provider, 0x2A4C, g.GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE)
            battery = await self._new_provider(0x180F)
            await self._characteristic(battery, 0x2A19, g.GattCharacteristicProperties.READ, b"\x64", encrypted=False)

            self.provider, self.report, self.consumer_report = provider, report, consumer
            self._listen(report, "read_requested", self._on_read)
            self._listen(consumer, "read_requested", self._on_consumer_read)
            self._listen(control, "write_requested", self._on_control)
            self._listen(report, "subscribed_clients_changed", lambda sender, args: self._schedule(self._subscriptions_changed))
            self._listen(consumer, "subscribed_clients_changed", lambda sender, args: self._schedule(self._subscriptions_changed))
            for item in self.providers:
                self._listen(item, "advertisement_status_changed", self._on_advertising)
        except BaseException:
            self._drop_services()
            raise

    def _drop_services(self):
        self._release_peer_device()
        for obj, event, token, callback in self.handlers:
            try:
                getattr(obj, f"remove_{event}")(token)
            except Exception:
                pass
        self.handlers.clear()
        self.report = self.consumer_report = self.provider = None
        self.consumer_target = None
        self.providers.clear()
        self.published.clear()

    def _on_read(self, sender, args):
        # Obtain the deferral on the callback thread, before returning to WinRT.
        deferral = args.get_deferral()
        self._schedule(self._read, args, deferral)

    def _on_consumer_read(self, sender, args):
        deferral = args.get_deferral()
        self._schedule(self._read, args, deferral, True)

    async def _read(self, args, deferral, consumer=False):
        self._metrics()["consumer_report_reads" if consumer else "mouse_report_reads"] += 1
        try:
            request = await args.get_request_async()
            if request is None:
                return
            value = HOME_RELEASE if consumer else bytes((self.buttons if self.active else 0, 0, 0, 0))
            if request.offset > len(value):
                request.respond_with_protocol_error(0x07)  # Invalid Offset
            else:
                request.respond_with_value(self.buffer(value[request.offset:]))
        finally:
            deferral.complete()

    def _on_control(self, sender, args):
        deferral = args.get_deferral()
        self._schedule(self._control, args, deferral)

    async def _control(self, args, deferral):
        self._metrics()["control_point_writes"] += 1
        try:
            request = await args.get_request_async()
            if request is None:
                return
            value = bytes(memoryview(request.value))
            valid = request.offset == 0 and value in (b"\x00", b"\x01")
            if valid:
                self.suspended = value == b"\x00"
                if self.suspended:
                    self.buttons = 0
                self._publish_status()
            if request.option == self.gatt.GattWriteOption.WRITE_WITH_RESPONSE:
                if valid:
                    request.respond()
                else:
                    request.respond_with_protocol_error(0x0D)
        finally:
            deferral.complete()

    def _clients(self, report=None):
        report = self.report if report is None else report
        return list(report.subscribed_clients) if report is not None else []

    def _consumer_clients(self):
        return list(self.consumer_report.subscribed_clients) if self.consumer_report is not None else []

    def _peer_ids(self):
        return {self._client_id(client) for client in self._clients() + self._consumer_clients()}

    def _eligibility(self, clients, allow_suspend=False):
        if self.starting:
            return False, 'starting'
        if not self.active:
            return False, 'stopped'
        if not self._advertising_running():
            return False, 'advertising_unavailable'
        self._refresh_link_state()
        if getattr(self, 'link_connected', None) is False:
            return False, 'link_disconnected'
        if self.suspended and not allow_suspend:
            return False, 'suspended'
        if len(self._peer_ids()) > 1 or len(clients) > 1:
            return False, 'multiple_peers'
        if not clients:
            return False, 'waiting_for_peer'
        if self.peer_id is None or self._client_id(clients[0]) != self.peer_id:
            return False, 'unapproved_peer'
        return True, 'ready'

    @staticmethod
    def _client_id(client):
        return client.session.device_id.id

    def _refresh_link_state(self):
        # CCCD subscriptions can survive a physical disconnect. This property
        # is a local snapshot, not a connect request or other radio operation.
        device = getattr(self, 'peer_device', None)
        if device is None:
            return
        try:
            state = enum_name(device.connection_status)
        except Exception:
            return  # Preserve the last known state if the snapshot is unavailable.
        if state in ('connected', 'disconnected'):
            connected = state == 'connected'
            if connected != self.link_connected:
                self.last_mouse_notify = None
            self.link_connected = connected
            if not self.link_connected:
                self.buttons = 0

    async def _peer_connection_changed(self, device, generation, peer_id):
        if (generation != self.generation or device is not self.peer_device
                or peer_id != self.peer_id or not self.active):
            return
        self._refresh_link_state()
        self._publish_status()

    def _release_peer_device(self):
        device = getattr(self, 'peer_device', None)
        handler = getattr(self, 'peer_device_handler', None)
        # Invalidate before removing the handler: a callback may already be queued.
        self.peer_device = self.peer_device_handler = self.peer_lookup = None
        self.link_connected = None
        self.last_mouse_notify = None
        if device is not None:
            if handler is not None:
                try:
                    device.remove_connection_status_changed(handler[0])
                except Exception:
                    pass
            try:
                device.close()
            except Exception:
                pass

    async def _retain_peer_device(self, peer_id):
        if self.peer_device is not None:
            return
        generation = self.generation
        lookup = (generation, peer_id)
        if self.peer_lookup == lookup:
            return
        self.peer_lookup = lookup
        device = None
        try:
            async with asyncio.timeout(3):
                device = await self.Device.from_id_async(peer_id)
            if device is None:
                return
            if (generation != self.generation or peer_id != self.peer_id
                    or not self.active):
                return
            self.peer_device = device
            # Keep the WinRT reference until stop; closing it immediately can
            # release Windows' connection reference while the service is active.
            def changed(sender, args):
                self._schedule(self._peer_connection_changed, device, generation, peer_id)
            try:
                token = device.add_connection_status_changed(changed)
                self.peer_device_handler = (token, changed)
            except Exception as exc:
                # Status polling still reads ConnectionStatus if events are unavailable.
                self._diagnostic_error('peer_connection_monitor', exc)
            self._refresh_link_state()
            try:
                self.peer_name = device.name or None
            except Exception:
                pass  # The display name is optional, unlike the pinned identity.
        except Exception:
            pass  # Lookup unavailable: keep link_connected unknown, not disconnected.
        finally:
            if self.peer_lookup == lookup:
                self.peer_lookup = None
            if device is not None and device is not self.peer_device:
                try:
                    device.close()
                except Exception:
                    pass

    def _advertising_running(self):
        return bool(self.providers) and all(
            enum_name(provider.advertisement_status) in ("started", "started_without_all_advertisement_data")
            for provider in self.providers
        )

    def _mouse_notification_interval(self):
        # ConnectionInterval is in 1.25 ms units, not milliseconds. Older
        # Windows SDKs/adapters may lack the API; disconnected parameters are 0.
        # https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.bluetoothleconnectionparameters.connectioninterval
        negotiated = None
        device = getattr(self, 'peer_device', None)
        if device is not None:
            try:
                units = device.get_connection_parameters().connection_interval
                if isinstance(units, int) and not isinstance(units, bool) and 6 <= units <= 3200:
                    negotiated = units * .00125
            except Exception:
                pass
        interval = max(MOUSE_NOTIFY_MIN_INTERVAL,
                       negotiated if negotiated is not None else MOUSE_NOTIFY_FALLBACK_INTERVAL)
        metrics = self._metrics()
        metrics['mouse_connection_interval_ms'] = round(negotiated * 1000, 3) if negotiated is not None else None
        metrics['mouse_notify_interval_ms'] = round(interval * 1000, 3)
        return interval

    def status(self):
        clients = self._clients()
        count = len(clients)
        consumer_clients = self._consumer_clients()
        advertising = enum_name(self.provider.advertisement_status) if self.provider is not None else "stopped"
        ready, reason = self._eligibility(clients)
        wake_ready, wake_reason = self._eligibility(consumer_clients, allow_suspend=True)
        self._mouse_notification_interval()
        return {"active": self.active, "advertising": advertising, "subscribers": count,
                "ready": ready, "peer_id": self.peer_id, "peer_name": self.peer_name,
                "link_connected": getattr(self, 'link_connected', None),
                "suspended": self.suspended, "reason": reason, "experimental": True,
                "wake_ready": wake_ready, "wake_reason": wake_reason,
                "wake_subscribers": len(consumer_clients),
                "providers": [{"uuid": str(getattr(getattr(p, "service", None), "uuid", "unknown")),
                               "advertising": enum_name(p.advertisement_status)} for p in self.providers],
                "diagnostics": dict(self._metrics())}

    def _publish_status(self):
        status = self.status()
        if status != self.last_status:
            self.last_status = status
            emit({"type": "event", "event": "status", **status})

    def _on_advertising(self, sender, args):
        # WinRT raises these off-loop. Snapshot event values immediately. This
        # adapter can report ABORTED/SUCCESS transiently before STARTED.
        self._schedule(self._advertising_changed, str(sender.service.uuid),
                       enum_name(args.status), enum_name(args.error), self.generation)

    async def _advertising_changed(self, service_id, status, error, generation):
        if generation != self.generation:
            return
        self.advertisement_errors[service_id] = error
        emit({"type": "event", "event": "advertising", "service": service_id,
              "status": status, "error": error})
        self._publish_status()
        if status == "aborted" and self.active and not self.starting:
            await asyncio.sleep(.5)
            if generation == self.generation and self.active and not self._advertising_running():
                await self.stop()
                detail = "Windows non ha mantenuto la pubblicazione" if error == "success" else error
                emit({"type": "event", "event": "error", "error": f"Pubblicazione Bluetooth interrotta: {detail}."})

    async def _subscriptions_changed(self):
        peers = self._peer_ids()
        if not self.active:
            self._publish_status()
            return
        if len(peers) != 1:
            self.buttons = 0
            self._publish_status()
            return
        client_id = next(iter(peers))
        if self.peer_id is None and (self.expected_peer is None or client_id == self.expected_peer):
            # Bind this activation to the first encrypted subscribed peer. Never
            # silently switch to another peer after a disconnect.
            self.peer_id = client_id
            self.peer_name = None
        if self.peer_id == client_id:
            await self._retain_peer_device(client_id)
        self._publish_status()

    async def probe(self):
        adapter = await self.Adapter.get_default_async()
        if adapter is None:
            return {"supported": False, "reason": "Nessun adattatore Bluetooth disponibile."}
        result = {"supported": bool(adapter.is_peripheral_role_supported and adapter.is_low_energy_supported),
                  "peripheral": adapter.is_peripheral_role_supported,
                  "low_energy": adapter.is_low_energy_supported,
                  "local_name": platform.node(), "hid_service": False, "experimental": True}
        if result["supported"]:
            await self._build()
            result["hid_service"] = True
        else:
            result["reason"] = "L'adattatore non supporta il ruolo periferica Bluetooth LE."
        return result

    async def start(self, expected_peer=None):
        if expected_peer is not None and (not isinstance(expected_peer, str) or not expected_peer or len(expected_peer) > 1024):
            raise ValueError("expected_peer deve essere un ID dispositivo valido.")
        if self.active:
            return self.status()
        result = await self.probe()
        if not result["supported"]:
            raise RuntimeError(result["reason"])
        self.generation += 1
        self.last_mouse_notify = None
        self.expected_peer = expected_peer
        self.peer_id = expected_peer
        self.peer_name = None
        self.buttons = 0
        self.suspended = False
        self.starting = True
        self.active = False
        self.advertisement_errors.clear()
        try:
            for provider in self.providers:
                parameters = self.gatt.GattServiceProviderAdvertisingParameters()
                parameters.is_discoverable = True
                parameters.is_connectable = True
                provider.start_advertising(parameters)
                self.published.add(str(provider.service.uuid))
            # StartAdvertising is asynchronous despite its void return type.
            # Require a confirmed stable state for both services; do not report
            # success merely because Windows accepted the method call.
            deadline = self.loop.time() + 6
            stable_since = None
            while self.loop.time() < deadline:
                if self._advertising_running():
                    stable_since = stable_since or self.loop.time()
                    if self.loop.time() - stable_since >= .2:
                        break
                else:
                    stable_since = None
                await asyncio.sleep(.05)
            else:
                states = ", ".join(f"{p.service.uuid}: {enum_name(p.advertisement_status)}" for p in self.providers)
                raise RuntimeError(f"Windows non riesce ad attivare il mouse Bluetooth ({states}).")
            self.starting = False
            self.active = True
            await self._subscriptions_changed()
        except BaseException:
            await self.stop()
            raise
        self._publish_status()
        return self.status()

    async def _notify(self, payload):
        metrics = self._metrics()
        metrics["mouse_notify_attempted"] += 1
        if any(payload):
            metrics["mouse_nonzero_reports_attempted"] += 1
        failure_reason = "api_exception"
        generation, peer, report = self.generation, self.peer_id, self.report
        try:
            # Serialize and pace the actual notifications, including every
            # chunk of a large move. API completion can mean queued by Windows,
            # so it cannot serve as Bluetooth flow control by itself.
            async with self.mouse_notify_lock:
                clients = self._clients()
                eligible, reason = self._eligibility(clients)
                if not eligible:
                    self.buttons = 0
                    failure_reason = reason
                    raise RuntimeError(f"Input mouse non disponibile: {reason}.")
                interval = self._mouse_notification_interval()
                last = self.last_mouse_notify
                if last is not None:
                    delay = last + interval - self.loop.time()
                    if delay > 0:
                        await asyncio.sleep(delay)
                # A stop, disconnect or new activation can occur during sleep.
                # Re-read subscribers and link state before sending anything.
                clients = self._clients()
                eligible, reason = self._eligibility(clients)
                if generation != self.generation or peer != self.peer_id or report is not self.report:
                    eligible, reason = False, 'session_changed'
                if not eligible:
                    self.buttons = 0
                    failure_reason = reason
                    raise RuntimeError(f"Input mouse non disponibile: {reason}.")
                self.last_mouse_notify = self.loop.time()
                notification = await report.notify_value_async(self.buffer(payload), clients[0])
                if notification.status != self.gatt.GattCommunicationStatus.SUCCESS:
                    self.buttons = 0
                    failure_reason = enum_name(notification.status)
                    raise RuntimeError(f"Invio Bluetooth fallito: {failure_reason}")
                metrics["mouse_notify_accepted"] += 1
        except Exception as exc:
            metrics["mouse_notify_failed"] += 1
            metrics["mouse_last_failure"] = failure_reason
            self._diagnostic_error("mouse_notify", exc, failure_reason)
            raise

    async def _consumer_notify(self, report, client, payload):
        notification = await report.notify_value_async(self.buffer(payload), client)
        if notification.status != self.gatt.GattCommunicationStatus.SUCCESS:
            raise RuntimeError(f"Invio Home Bluetooth fallito: {enum_name(notification.status)}")

    async def _release_consumer(self, target):
        report, client, generation, peer = target
        # Release only the same captured recipient. This remains safe if an
        # unrelated second subscriber appeared after the press: no input is
        # sent to that second subscriber and a held Home key can still clear.
        if self.generation != generation or self.peer_id != peer or self._client_id(client) != peer:
            raise RuntimeError('Sessione Bluetooth cambiata durante il comando Home.')
        async with asyncio.timeout(2):
            await self._consumer_notify(report, client, HOME_RELEASE)

    async def wake(self):
        clients = self._consumer_clients()
        eligible, reason = self._eligibility(clients, allow_suspend=True)
        if not eligible:
            raise RuntimeError(f"Richiamo Bluetooth non disponibile: {reason}.")
        target = (self.consumer_report, clients[0], self.generation, self.peer_id)
        self.consumer_target = target
        released = False
        try:
            # No automatic press retry: repeating Home can cause another action.
            async with asyncio.timeout(2):
                await self._consumer_notify(target[0], target[1], HOME_PRESS)
            await asyncio.sleep(.08)
            await self._release_consumer(target)
            released = True
            return {'sent': True, 'effect': 'unverified', 'action': 'home', 'reports': 2}
        finally:
            if not released:
                try:
                    await self._release_consumer(target)
                except Exception:
                    pass
            if self.consumer_target is target:
                self.consumer_target = None

    async def input(self, command, message):
        new_buttons = self.buttons
        dx = dy = wheel = 0
        if command == "move":
            dx = require_int(message.get("dx", 0), "dx", -MAX_DELTA, MAX_DELTA)
            dy = require_int(message.get("dy", 0), "dy", -MAX_DELTA, MAX_DELTA)
            self._metrics()["mouse_move_commands"] += 1
        elif command == "buttons":
            new_buttons = require_int(message.get("buttons"), "buttons", 0, 7)
            self._metrics()["mouse_button_commands"] += 1
        elif command == "wheel":
            wheel = require_int(message.get("delta", 0), "delta", -MAX_DELTA, MAX_DELTA)
        elif command == "release":
            new_buttons = 0
        count = 0
        for payload in mouse_reports(new_buttons, dx, dy, wheel):
            await self._notify(payload)
            self.buttons = new_buttons
            count += 1
        return {"sent": True, "reports": count, "buttons": self.buttons}

    async def stop(self):
        if self.stopping:
            return self.status()
        self.stopping = True
        try:
            if self.consumer_target is not None:
                try:
                    await self._release_consumer(self.consumer_target)
                except Exception:
                    pass
                self.consumer_target = None
            if self.active and self.buttons:
                try:
                    async with asyncio.timeout(2):
                        await self._notify(b"\x00\x00\x00\x00")
                except Exception:
                    pass
            self.active = False
            self.starting = False
            self.generation += 1
            self.buttons = 0
            self.suspended = False
            for provider in self.providers:
                service_id = str(provider.service.uuid)
                if service_id not in self.published:
                    continue
                # StopAdvertising is asynchronous too: the native status can
                # remain STARTED briefly, so track each stop request ourselves
                # instead of issuing duplicate stops based on that stale state.
                self.published.discard(service_id)
                try:
                    provider.stop_advertising()
                except Exception as exc:
                    emit({"type": "event", "event": "error", "error": f"Arresto Bluetooth: {exc}"})
            await asyncio.sleep(.25)
            self.peer_id = self.peer_name = self.expected_peer = None
            # Release the local GATT handles as well as requesting StopAdvertising.
            # A fresh activation rebuilds the service; stale driver state cannot
            # make a stopped provider look ready on the next start.
            self._drop_services()
            self._publish_status()
            return self.status()
        finally:
            self.stopping = False

    async def close(self):
        await self.stop()
        self._drop_services()
        for task in list(self.callback_tasks):
            task.cancel()
        if self.callback_tasks:
            await asyncio.gather(*self.callback_tasks, return_exceptions=True)

    async def command(self, message):
        command = message.get("command", message.get("cmd"))
        if command == "probe":
            return await self.probe()
        if command == "start":
            return await self.start(message.get("expected_peer"))
        if command in ("stop", "quit"):
            return await self.stop()
        if command == "status":
            return self.status()
        if command == "wake":
            return await self.wake()
        if command in ("move", "buttons", "wheel", "release"):
            return await self.input(command, message)
        raise ValueError("Comando sconosciuto.")


async def run_worker():
    worker = MouseWorker()
    queue = asyncio.Queue(maxsize=256)
    loop = asyncio.get_running_loop()

    def read_stdin():
        try:
            while True:
                line = sys.stdin.readline(65537)
                if not line:
                    break
                # Backpressure prevents unbounded queued movement if UI is busy.
                future = asyncio.run_coroutine_threadsafe(queue.put(line), loop)
                future.result()
        except (OSError, ValueError, RuntimeError):
            pass
        finally:
            try:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)
            except RuntimeError:
                pass

    threading.Thread(target=read_stdin, name="AirFrameMouse-stdin", daemon=True).start()
    emit({"type": "event", "event": "ready", "protocol": 1, "experimental": True})
    try:
        while True:
            line = await queue.get()
            if line is None:
                break
            message = None
            try:
                if len(line) > 65536 or not line.endswith("\n"):
                    raise ValueError("Riga JSON non valida o troppo lunga.")
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("Il comando deve essere un oggetto JSON.")
                async with asyncio.timeout(COMMAND_TIMEOUT):
                    result = await worker.command(message)
                emit({"type": "response", "id": message.get("id"), "ok": True, "result": result})
                if message.get("command", message.get("cmd")) == "quit":
                    break
            except Exception as exc:
                if isinstance(exc, TimeoutError):
                    await worker.stop()
                emit({"type": "response", "id": message.get("id") if isinstance(message, dict) else None,
                      "ok": False, "error": str(exc) or "Operazione Bluetooth scaduta."})
    finally:
        await worker.close()


def main():
    try:
        asyncio.run(run_worker())
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        emit({"type": "event", "event": "fatal", "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
