# Modifiche

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
