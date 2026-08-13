# DexcomService con Dexcom G7

Il servizio legge i valori del sensore **Dexcom G7** dal servizio Dexcom Share.
Il G7 usa lo stesso backend Share delle versioni precedenti: non serve il
numero seriale del trasmettitore, ma Share deve essere attivo nell'app Dexcom
G7 e deve essere configurato almeno un follower.

## Configurazione

1. Nell'app Dexcom G7 aprire **Connessioni > Share**, attivare Share e invitare
   almeno un follower.
2. Copiare `.env.example` in `.env`.
3. Inserire in `DEXCOM_USERNAME` e `DEXCOM_PASSWORD` le credenziali
   dell'account **principale Dexcom G7** che pubblica i dati, non quelle del
   follower.
4. Impostare `DEXCOM_REGION=US` per un account statunitense oppure
   `DEXCOM_REGION=OUS` per un account italiano/internazionale.
5. Installare le dipendenze con `pip install -r requirements.txt` e avviare con
   `gunicorn wsgi:app`.

## Deploy su Render

Il file `render.yaml` crea un Web Service con un solo worker (per evitare più
processi di sincronizzazione), configura `/health` come health check e richiede
le variabili segrete nella dashboard Render. Dopo aver collegato il repository,
selezionare **New > Blueprint**, scegliere il repository e valorizzare tutte le
variabili marcate come segrete. Ogni push sul branch collegato avvierà il deploy.

Le route `/glicemia`, `/pianifica-ping` e il processo di sincronizzazione verso
MongoDB utilizzano tutte la configurazione G7 centralizzata.

## Nota

Dexcom Share è un servizio cloud e richiede che il telefono con l'app G7 abbia
una connessione a Internet. Questo progetto non sostituisce le indicazioni o
gli allarmi del dispositivo Dexcom e non deve essere usato per decisioni
terapeutiche.
