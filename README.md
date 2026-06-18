# Vertical Project Share

Plugin QGIS per **condividere e versionare** i progetti QGIS archiviati su **PostgreSQL**.

Quando un progetto è salvato nello storage nativo PostgreSQL di QGIS (tabella
`qgis_projects`), più utenti possono lavorarci sopra. Questo plugin aggiunge uno
**storico delle versioni** e una **notifica di disallineamento**, così le
modifiche di un utente non vengono perse silenziosamente.

> ⚠️ Stato: `experimental`. Baseline Qt5 / QGIS 3.x. Il port a Qt6 / QGIS 4 e i
> miglioramenti di logica del versionamento sono pianificati su branch separati
> (vedi *Limitazioni note*).

## Requisiti

- QGIS ≥ 3.22 (Qt5)
- Un progetto QGIS salvato su **PostgreSQL** (storage `postgresql`)
- Modulo Python `psycopg2` disponibile nell'ambiente Python di QGIS

## Installazione

Il plugin vero e proprio è la cartella `vertical_projectshare/`. Copiala nella
directory dei plugin QGIS:

| SO | Percorso |
|----|----------|
| Linux | `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/` |
| Windows | `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\` |
| macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/` |

Poi riavvia QGIS (o *Plugin → Ricarica plugin*) e abilitalo da
*Plugin → Gestisci e installa plugin*.

## Uso

La barra degli strumenti **VerticalShare** espone:

| Comando | Funzione |
|---------|----------|
| Versionamento attivo | Attiva/disattiva il versionamento: a ogni salvataggio propone uno snapshot e controlla periodicamente il DB |
| Lista snapshot | Apre lo storico delle versioni del progetto |
| Ricarica versione aggiornata dal db | Ricarica dal DB l'ultima versione corrente |
| Verifica aggiornamenti su db | Controlla subito se sul DB esiste una versione più recente |
| Salva copia locale in QGZ | Esporta il progetto corrente in un file `.qgz` |
| ℹ️ Informazioni | Mostra versione e istruzioni d'uso |

Nella **finestra storico** ogni versione può essere *promossa* a copia corrente
per tutti, *scaricata* come `.qgz`, oppure *eliminata*.

I comandi si attivano solo quando il progetto aperto è su PostgreSQL.

## Struttura dati

Il plugin crea, nello schema del progetto, la tabella
`qgis_projects_share_history` con: nome progetto, contenuto (`BYTEA`), metadata,
autore, data, note e checksum md5 di ogni snapshot.

## Limitazioni note

Tracciate nelle issue del repository:

- Concorrenza solo *notificata*, non *prevenuta* (manca il controllo
  ottimistico in scrittura).
- Snapshot acquisito tramite polling del DB anziché dai byte salvati.
- Confronto di stato sensibile a timestamp/autore oltre che al contenuto.
- `promote` sovrascrive la copia viva senza archiviarla prima.
- Compatibilità Qt6 / QGIS 4 non ancora implementata.

## Licenza

Vertical Srl — https://vertical-srl.it
