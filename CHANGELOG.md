# Modifiche

## 1.2.0 — 05/11/2026

- **Nuovo nome: NEON VERBALE** (prima *Trascrittore riunioni*), con icona synthwave (piuma al
  neon su un sole a strisce), banner e immagini del wizard di installazione nello stesso stile.
  Il repository è ora `battles5/neon-verbale`; i vecchi link vengono reindirizzati da GitHub.
- **Aggiornamento senza perdite:** il setup si installa sopra *Trascrittore riunioni* (stesso
  identificativo), toglie i vecchi collegamenti dal menu Start e dal desktop e, al primo avvio,
  sposta la cartella dati (voci, glossario, tempi, modelli) sotto il nuovo nome.
- Guida con i colori del nuovo stile.

## 1.1.0 — 05/11/2026

- **Coda di registrazioni.** "Aggiungi video…" resta attivo anche durante un'elaborazione e i
  video si accodano senza limiti, in una lista che scorre. "Avvia tutti" mette in coda tutto ciò
  che è in attesa: finché la coda è attiva, anche i video aggiunti dopo entrano da soli. Su ogni
  riga, ▶ avvia quel video (o lo mette per primo in coda) e ✕ lo toglie dalla lista. Lo stesso
  video non può essere in lista due volte.
- **ETA totale** di tutto quello che resta da fare, ricalcolata a ogni aggiunta o rimozione,
  oltre all'ETA e alla posizione in coda di ogni video.
- **Tema chiaro o scuro** come quello di Windows (letto all'avvio), con la barra del titolo
  scura nel tema scuro. Nuove dipendenze: sv-ttk (MIT) e darkdetect (BSD-3-Clause).
- "Apri cartella risultati" apre la cartella dell'ultimo video completato.

## 1.0.1 — 22/10/2026

- **Corretto il blocco della finestra dopo la scelta di un video.** La stima dei tempi e il
  rilevamento della scheda video caricavano PyTorch e faster-whisper nel thread della finestra,
  mentre un altro thread caricava le stesse librerie CUDA. Al primo avvio dopo l'accensione questo
  può richiedere più di un minuto, e Windows segnava la finestra come "Non risponde". Ora queste
  operazioni girano in sottofondo, una alla volta: la finestra risponde subito, la riga del file
  mostra "calcolo della stima…" e "Avvia" si attiva quando la stima è pronta.
- I video trascinati sull'icona aprono subito la finestra, invece di aspettare la stima.
- L'etichetta "nomi + voci" non resta più accesa dopo la fine della lettura dei nomi.
- Verificato con le registrazioni dello schermo di Windows (Strumento di cattura: mp4 H.264
  1672×1420 a 30 fps, audio AAC stereo 48 kHz).

## 1.0.0 — 21/10/2026

Prima versione pubblica.
