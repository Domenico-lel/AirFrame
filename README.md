# AirFrame

Duplica lo schermo dell’iPhone su Windows usando **AirPlay**, senza installare app sul telefono. Il video appare in una finestra con cornice del dispositivo e può essere affiancato a un controllo mouse Bluetooth sperimentale.

**Stato: prototipo Windows x64.** La ricezione video e il controllo mouse sono stati provati su un iPhone reale. Il mouse è stato segnalato come lento e impreciso: l’ultima versione introduce pacing Bluetooth e Raw Input, ma il miglioramento sul telefono deve ancora essere confermato. macOS e Android non sono ancora supportati.

## Download e avvio

1. Scarica il pacchetto ZIP dalla pagina [Release](https://github.com/Domenico-lel/AirFrame/releases).
2. Estrai tutta la cartella e apri `AirFrame.exe`. Mantieni accanto `AirFrameMouse.exe`, `_internal` ed `engine`.
3. Collega PC e iPhone alla stessa rete locale; il PC può usare Ethernet.
4. Sull’iPhone apri **Centro di Controllo → Duplica schermo → AirFrame** e inserisci l’eventuale codice mostrato sul PC.

Se il ricevitore non compare, apri le impostazioni di AirFrame e usa la configurazione della rete locale. Lo script richiede il normale consenso amministratore per creare regole firewall limitate alla sottorete locale.

## Funzioni

- Ricezione AirPlay attraverso il motore open source UxPlay.
- Cornice scelta dal modello comunicato dal dispositivo, con fallback generico e selezione manuale. Il catalogo dei modelli è limitato; non identifica ogni telefono dalla sola risoluzione.
- Adattamento del video al rapporto e all’orientamento ricevuti.
- Finestra mantenuta durante l’interruzione del flusso e pulsante per ripristinare il ricevitore video.
- Mouse Bluetooth LE tramite AssistiveTouch: movimento relativo, clic e trascinamento; rotella sperimentale.
- Velocità del puntatore regolabile dal 25% al 300%; **Maiusc** per movimenti fini, **Esc** per tornare al PC.
- Tentativo esplicito di richiamo tramite tasto Home Bluetooth, indipendente dal video.

## Controllare l’iPhone con il mouse

Serve un adattatore PC che supporti **Bluetooth LE peripheral role** e il servizio HID. Il collegamento video e quello del mouse sono separati.

1. Premi il pulsante mouse nella barra e scegli **Collega il PC via Bluetooth**.
2. Sull’iPhone attiva **Impostazioni → Accessibilità → Tocco → AssistiveTouch**.
3. Apri **Dispositivi → Dispositivi Bluetooth** e seleziona il computer.
4. Completa anche l’eventuale notifica Windows **Aggiungi un dispositivo**, verificando il codice sui due dispositivi.
5. Con il video in diretta premi **Usa mouse**. Regola la velocità nel pannello se necessario.

Il PC si presenta come periferica di controllo: non occorrono un altro mouse da abbinare al telefono o un’app iOS. Il controllo è relativo; un clic sul video non equivale automaticamente a un tocco alle stesse coordinate sull’iPhone. Tastiera completa e multitouch non sono implementati.

## Blocco e richiamo: limiti attuali

AirFrame mantiene la propria finestra quando il telefono smette di trasmettere. iOS può però interrompere AirPlay: in quel caso occorre selezionare nuovamente AirFrame in Duplica schermo sul telefono.

**Prova richiamo · tasto Home** invia una pressione e un rilascio HID. Un invio riuscito non conferma che il telefono si sia svegliato, sbloccato o abbia ripreso il video. Face ID o codice restano necessari quando richiesti da iOS. Il richiamo effettivo dopo il blocco non è ancora verificato; non è disponibile uno sblocco remoto garantito.

## Sviluppo

Richiede Windows x64 e Python 3.11. I sorgenti del motore modificato sono in `source/UxPlay`, con riferimento upstream, patch e manifest delle dipendenze in `source/`.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Per eseguire `app.py`, prepara anche `engine/uxplay.exe` e il relativo runtime: puoi usare la cartella `engine` del pacchetto Windows della stessa versione oppure compilarla seguendo [source/BUILD.md](source/BUILD.md).

```powershell
.venv\Scripts\python app.py
```

Test senza collegarsi al telefono:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.venv\Scripts\python -m unittest discover -s . -p 'test_*.py' -q
Remove-Item Env:QT_QPA_PLATFORM
```

Il target attuale ha superato **43 test automatici** e prove native isolate del percorso mouse. I test simulati non misurano la latenza reale del collegamento all’iPhone. Dettagli in [VERIFICA.md](VERIFICA.md).

Per generare i due eseguibili:

```powershell
.venv\Scripts\python -m PyInstaller --noconfirm AirFrame.spec
```

Completa `dist/AirFrame` con `engine`, `Configura-rete.ps1`, documentazione e licenze, come descritto nella guida di compilazione. Gli eseguibili e le dipendenze compilate sono distribuiti nelle Release; il repository contiene i sorgenti e i manifest.

## Dati e licenza

Il programma non richiede un account o un server cloud. Audio e video viaggiano nella rete locale; il mouse usa Bluetooth. Preferenze, registrazioni dei dispositivi, chiave del ricevitore e log vengono salvati localmente in `%LOCALAPPDATA%\AirFrame` e non fanno parte del repository.

AirFrame è distribuito con licenza **GPL-3.0-or-later**. Vedi [LICENSE](LICENSE) e [THIRD_PARTY.md](THIRD_PARTY.md) per componenti, licenze e riferimenti. Il progetto non è affiliato o certificato da Apple.
