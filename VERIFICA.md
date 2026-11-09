# Stato del prototipo Windows

## Verificato in questa sessione

- Compilazione nativa x64 di UxPlay modificato con MSYS2 UCRT64, GCC, CMake e Ninja.
- Avvio del ricevitore con il runtime multimediale copiato accanto all'app, senza dipendenza dal PATH di MSYS2.
- Disponibilità dei decoder H.264/AAC e dell'uscita audio WASAPI.
- Risposta RTSP `/info`: 200 OK, identità del ricevitore AirFrame e descrizione AirPlay valida come plist binario.
- Risposta mDNS `_airplay._tcp.local` contenente AirFrame sulla rete locale del PC di sviluppo.
- Video sintetico GStreamer a 393 × 852 incorporato nella cornice attraverso una finestra nativa Direct3D11: uscita normale, codice 0. Non era uno stream iPhone.
- Sei test di logica passati: modello esatto, fallback sconosciuto, cambio dispositivo, preferenze per dispositivo, geometria senza deformazione e pausa/ripresa dell'interfaccia.
- Controllo visivo di attesa, video sintetico, finestra piccola, orientamento orizzontale e impostazioni.
- Avvio del pacchetto AirFrame.exe da una cartella di lavoro diversa, con runtime incluso: ricevitore pronto, screenshot generato, uscita normale codice 0. Corretta una collisione ICU del PATH del computer di compilazione; AirFrame.spec conserva la correzione.

## Confermato dall'utente

- Ricezione reale dello schermo iPhone. La conferma non comprende audio, modello, rotazione, PIN o comportamento dopo il blocco.
- Abbinamento Bluetooth: la foto mostrava la richiesta Windows «Aggiungi un dispositivo» ancora da completare; dopo la conferma, l'utente ha riportato «PC collegato · pronto per controllare l'iPhone». Questo conferma lo stato di sottoscrizione rilevato dall'app, non ancora movimento/clic ricevuti da iOS.

## Mouse sperimentale: verifiche locali

- Probe sul PC: ruolo periferica Bluetooth LE e disponibilità del servizio HID 0x1812 riusciti. Non costituiscono un abbinamento iPhone.
- Overlay trasparente Qt sopra il video nativo D3D: verificati requisiti di attivazione, Escape, perdita del focus, disconnessione e rilascio con pulsanti a zero. Non erano input ricevuti da iOS.
- Worker Bluetooth: creazione completa HID/GATT, pubblicazione reale nello stato STARTED, arresto, secondo avvio e uscita pulita verificati sul PC. Nessun input inviato a un telefono durante questa verifica. Gestito uno stato ABORTED transitorio del driver durante l'avvio.
- Undici test locali passati: i sei del ricevitore e cinque su report HID, clic veloci, rilascio con Esc, accumulo degli spostamenti e rifiuto di un dispositivo diverso.
- Pacchetto AirFrameMouse.exe: stessi test reali di pubblicazione/arresto/riavvio superati, uscita codice 0. Verificato anche il collegamento QProcess tra controller Qt e helper confezionato. Interfaccia AirFrame.exe avviata correttamente con runtime incluso. L'abbinamento e gli input sul telefono restano da provare.

## Richiamo sperimentale: verifiche locali

- 22 test complessivi superati, inclusi struttura dei report mouse/Home, destinatario unico, Home consentito durante sospensione, rilascio dopo errore e conservazione del collegamento Bluetooth dopo un comando mouse rifiutato durante il blocco.
- Nessun comando Home inviato a un iPhone durante i test automatici. I test simulati verificano il codice e l'ordine dei messaggi, non il risveglio fisico o la ripresa AirPlay.
- Nuovo helper confezionato: creazione di entrambi i report HID, pubblicazione Bluetooth, arresto e riavvio verificati sul PC con uscita normale. Interfaccia della procedura fotografata e controllata integralmente.

## Correzioni dopo la prova utente

- Eliminato l'alias PyWinRT deprecato: viene usato notify_value_async(value, subscribed_client), sempre mirato a un solo destinatario. Gli avvisi su stderr vanno nel log e non sostituiscono lo stato di connessione.
- 24 test locali superati, inclusi il falso errore da warning e il ripristino del ricevitore che preserva lo stato Bluetooth.
- Video animato sintetico verificato prima/durante/dopo cattura mouse: l'immagine continua a cambiare. Nessun congelamento riprodotto nel solo overlay Direct3D.
- Il log reale ha confermato la chiusura interna di una connessione inattiva a 60 secondi, precedente a reset120. Modificati gli argomenti a -nc no -nofreeze -reset45 per ricreare il renderer e anticipare quel percorso; aggiunto Ripristina video AirPlay. Riconnessione e controllo effettivo su iPhone dopo questa correzione restano da verificare.

## Riscontro successivo sul mouse

- L'utente conferma video aggiornato, ma nessun controllo con il mouse. Non risolto al momento di questa verifica.
- Il log reale mostra 1973 notifiche mouse accettate da WinRT, zero errori. Il telefono scrive anche Suspend/Exit Suspend sul Control Point. L'accettazione delle notifiche non prova che iOS esegua gli input.
- Test nativo isolato dei movimenti (senza AirPlay o Bluetooth): 40 movimenti, 40 eventi, somme preservate nella coda e nei report HID; nessun movimento inverso dovuto al ricentramento. File di sviluppo: work/verify_mouse_input_motion.py e work/mouse-input-motion-results.json.
- Il volume veniva regolato manualmente dall'utente e non costituisce prova di un errore di mappatura HID.
- Lo stato effettivo di AssistiveTouch sull'iPhone non è leggibile tramite il solo collegamento attuale: nessun iPhone USB presente. Richiesta verifica dell'interruttore; l'abbinamento non basta.

## Precisione e ritardo del mouse

- Nuovo riscontro dell'utente: il controllo funziona, ma è estremamente lento e impreciso. Il precedente problema di assenza completa del controllo non è più riprodotto dall'utente; la causa esatta non è stata dimostrata.
- Il log successivo registra oltre 9.000 notifiche mouse accettate, con picchi di oltre 300 al secondo. Aggiunto pacing per ogni notifica, compresi i report suddivisi; l'accettazione di WinRT non viene più usata da sola come controllo del flusso.
- Il controller invia un solo pacchetto HID per comando; i residui restano nella coda locale, cancellabile da Esc. Pressione e rilascio mantengono il proprio ordine.
- Raw Input relativo evita l'accelerazione aggiunta dal cursore Windows e ignora il ricentramento. Rimane un fallback Qt per dispositivi assoluti o API non disponibili. Aggiunti velocità 25–300% e Maiusc per precisione con resto frazionario conservato.
- Il riferimento BluetoothLEDevice rimane aperto fino allo stop: una disconnessione nota blocca mouse e Home anche se Windows conserva le sottoscrizioni. Stato non disponibile distinto da stato disconnesso.
- Il miglioramento reale della latenza sull'iPhone resta da misurare dopo questo aggiornamento.
- 43 test automatici superati dopo queste modifiche. Prova nativa isolata WM_INPUT: movimenti positivi e negativi esatti, nessun duplicato con gli eventi Qt, nessun movimento prodotto dal ricentramento, frazioni conservate al 25%, registrazione rimossa e cursore ripristinato all'uscita. Percorso fallback Qt verificato separatamente.

## Da verificare con l'iPhone dell'utente

- Dettagli del primo abbinamento con PIN.
- Audio reale, sincronizzazione e latenza.
- Modello comunicato dall'iPhone 14 Pro e selezione automatica del relativo profilo.
- Rotazione durante una sessione reale.
- Blocco breve, sblocco, blocco prolungato e ritorno alla sessione. La continuità non può essere garantita dal ricevitore se iOS chiude il collegamento.
- Comportamento con notifiche, chiamate e app che limitano l'uscita video.
- Abbinamento del PC in AssistiveTouch, comparsa del puntatore, movimento relativo, clic, trascinamento e rotella sperimentale.
- Ritorno del mouse al PC con Esc durante una sessione reale, perdita Bluetooth/video e blocco dell'iPhone.
- Sottoscrizione del nuovo report Consumer/Home, possibile necessità di nuovo abbinamento, risveglio del display dopo blocco e ripresa o interruzione della sessione AirPlay. Il comando Home è sperimentale, non una funzione già collaudata sull'iPhone.

## Non implementato

Ricezione Android; pacchetto macOS; tastiera completa remota; sblocco remoto autenticato; riavvio remoto di Duplica schermo; pubblicazione negli store; certificazione AirPlay. Il tentativo di risveglio Home/Bluetooth è implementato ma non verificato sull'iPhone. Questa è una build locale di sviluppo.
