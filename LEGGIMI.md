# AirFrame — prototipo Windows

Ricevitore AirPlay con cornice del telefono. Non richiede app sull'iPhone.

## Avvio

1. Apri AirFrame.exe lasciandolo nella sua cartella, accanto a AirFrameMouse.exe, engine e _internal.
2. Usa la stessa rete locale per PC e iPhone. Il PC può essere collegato via Ethernet al medesimo router.
3. Se AirFrame non appare, apri Impostazioni > Configura accesso alla rete locale e conferma il normale avviso amministratore Windows. La regola è limitata alla sottorete locale; non disattiva il firewall. Gli errori della procedura vanno verificati prima di considerarla completata.
4. Su iPhone apri Centro di Controllo > Duplica schermo > AirFrame.
5. Inserisci il codice mostrato nella finestra. Continua a usare il telefono normalmente.

Non servono account o server cloud. Audio e video viaggiano nella rete locale. Il ricevitore resta acceso finché AirFrame è aperto. Chiudere la finestra termina il ricevitore.

## Mouse Bluetooth sperimentale

La ricezione reale dello schermo è stata confermata dall'utente. Il controllo mouse è una funzione separata e sperimentale. Il controllo mouse è stato confermato su un iPhone reale, ma è stato segnalato come lento e impreciso. L'ultimo aggiornamento introduce Raw Input e pacing Bluetooth: il miglioramento sul telefono e il richiamo dopo il blocco restano da verificare.

1. Premi il pulsante mouse nella barra di AirFrame, poi «Collega il PC via Bluetooth».
2. Sull'iPhone apri Impostazioni → Accessibilità → Tocco → AssistiveTouch. Attivalo, poi apri Dispositivi → Dispositivi Bluetooth.
3. Abbina il PC, normalmente indicato con il nome del computer Windows. Se Windows mostra «Aggiungi un dispositivo — Toccare per configurare l'iPhone», apri la notifica e completa l'abbinamento anche sul PC, confermando l'eventuale codice corrispondente sui due dispositivi.
4. Con Duplica schermo attivo e «PC collegato» nella finestra di configurazione, premi «Usa mouse».
5. Premi Esc per restituire il mouse al PC. Per terminare la pubblicazione Bluetooth usa «Disattiva controllo Bluetooth».

Non serve un'app sull'iPhone e non occorre un altro mouse o accessorio: AirFrame fa presentare il PC come dispositivo di controllo. Serve il Bluetooth LE del PC con ruolo periferica e servizio HID. Il video continua a usare AirPlay sulla rete locale; il puntatore usa Bluetooth. Muovi il puntatore relativo dell'iPhone, fai clic e trascina; la rotella è sperimentale. La posizione del mouse sul video non diventa un tocco alle stesse coordinate. Non sono disponibili tastiera completa, sblocco o riavvio di Duplica schermo da remoto. Il controllo mouse viene rilasciato se il video o il collegamento mouse non sono disponibili, oppure se la finestra perde il focus.

## Precisione del mouse

Nel pannello mouse trovi «Velocità puntatore» (25–300%, ricordata tra gli avvii). Abbassala se superi le icone, alzala se il puntatore percorre troppo poco spazio. Durante il controllo tieni premuto Maiusc per movimenti fini a un quarto della velocità. Il movimento usa Windows Raw Input quando disponibile, evitando l'accelerazione del puntatore di Windows; iOS mantiene la propria gestione del puntatore. I movimenti vengono raggruppati e ogni notifica rispetta l'intervallo Bluetooth negoziato (minimo 16,67 ms, fallback 30 ms). Esc scarta il movimento ancora in attesa e restituisce il mouse al PC.

## Richiamo dal PC: prova sperimentale

Dopo l'abbinamento diretto tra PC e iPhone, apri il pulsante mouse nella barra e premi «Prova richiamo · tasto Home». Il pulsante funziona indipendentemente dalla presenza del video, ma richiede che iPhone mantenga il canale Bluetooth per questo comando. Invia una singola pressione e rilascio del tasto Home; non invia codici di sblocco. Se il telefono è già attivo può riportarlo alla Home.

Il risultato positivo significa che il comando è stato inviato: il risveglio fisico e la ripresa del video vanno verificati sull'iPhone. Face ID o codice restano necessari quando richiesti da iOS. Se iOS ha chiuso AirPlay, il comando non riavvia automaticamente Duplica schermo. Se il pulsante rimane disabilitato dopo un vecchio abbinamento, dissocia il PC dall'iPhone e abbinalo nuovamente per aggiornare il profilo Bluetooth.

Base tecnica: [Apple Accessory Design Guidelines, tabella 14-3](https://developer.apple.com/accessories/Accessory-Design-Guidelines.pdf), Consumer Menu 0x0040 corrispondente a Home; [Bluetooth HOGP §4.10](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/hogp_v1-2_1777405843/HOGP_v1.2/out/en/index-en.html), flag RemoteWake. Queste specifiche non garantiscono l'interoperabilità del prototipo con iOS.

## Cornice

Il codice modello comunicato da AirPlay sceglie il profilo quando presente nel catalogo. iPhone15,2 corrisponde a iPhone 14 Pro. Non deduciamo il modello dalla risoluzione, perché non è un identificativo affidabile. Per un modello sconosciuto viene usata una cornice generica; puoi assegnare un profilo dalle impostazioni. La scelta viene ricordata per l'identità comunicata dal dispositivo (che può cambiare).

Prima della connessione la cornice di anteprima è iPhone 14 Pro, il dispositivo del primo utente; non è un dispositivo già rilevato. Le cornici sono ricostruzioni stilizzate, non riproduzioni ufficiali o dimensionalmente certificate. Il rapporto del video ricevuto e l'orientamento prevalgono sul profilo, per evitare stiramenti e ritagli. Island/notch decorativi sono statici e disattivabili se già presenti nel video; possono coprire l'area sottostante.

## Blocco e sblocco

La finestra rimane aperta quando il flusso si interrompe. Il ricevitore viene resettato dopo 45 secondi senza heartbeat, prima della pulizia interna delle connessioni a 60 secondi; il renderer viene ricreato anziché conservare una vecchia immagine. Non significa che iOS mantenga necessariamente la trasmissione: se iOS chiude la sessione, seleziona nuovamente AirFrame in Duplica schermo. Per recuperare un video fermo usa «Ripristina video AirPlay» dalla finestra del controllo: viene riavviato soltanto il ricevitore video, mantenendo Bluetooth e cornice. Il programma non riavvia Duplica schermo sull'iPhone e non esegue lo sblocco autenticato da remoto.

## Limiti del prototipo

- Windows x64 è il primo target. macOS non è ancora confezionato o collaudato.
- Android non è supportato da questo ricevitore. Miracast/Google Cast richiedono un progetto distinto e dipendono dalle capacità del telefono.
- Contenuti protetti e app che limitano l'uscita video possono mostrare nero o adottare modalità diverse.
- Il mouse richiede attivazione esplicita, AssistiveTouch e Bluetooth compatibile; resta sperimentale. La tastiera remota non è implementata.
- Qualità e latenza dipendono dalla rete e vanno misurate con un dispositivo reale.
- Richiede una rete che permetta mDNS e comunicazione tra dispositivi. VPN e reti ospiti con isolamento possono impedirlo.

## Diagnostica e privacy

Impostazioni e log sono in %LOCALAPPDATA%\AirFrame. receiver.log registra anche gli stati Bluetooth e i conteggi delle notifiche mouse inviate/accettate/rifiutate, senza salvare coordinate o contenuti dei comandi. I log del ricevitore possono contenere nome, modello e identificatori del dispositivo ricevuti da UxPlay. Non vengono caricati su Internet. Non viene registrato il video. La cartella contiene anche le informazioni di abbinamento: non condividerla integralmente; rimuovi dati personali dai log prima di inviarli.

## Sorgenti

app.py e profiles.py contengono l'interfaccia; bluetooth_mouse.py, mouse_control.py e mouse_overlay.py aggiungono il mouse sperimentale; source/UxPlay contiene il ricevitore modificato. Le modifiche aggiungono incorporamento HWND ed eventi per identità, dimensioni, PIN e presenza di fotogrammi. requirements.txt elenca il runtime Python. Vedi source/BUILD.md per ricompilare.
