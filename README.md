# Baby melk-dashboard

Een kleine Flask-app met:

- SQLite-opslag op disk
- login voor invoer/verwijderen
- dashboard met dagtotalen
- grafiek per dag, met aan/uit zetten van individuele dagen
- mobielvriendelijke invoer

## Snel draaien

```bash
docker compose up -d --build
```

Open daarna:

```text
http://<jouw-host>:8080
```

## Inlog

Zet in `docker-compose.yml` of via Portainer:

- `SECRET_KEY` = lange random string
- `ADMIN_PASSWORD` = eigen wachtwoord

## Opslag

De database staat in de volume-mount `/data/babylog.db`.

## Handig voor Proxmox / Portainer

Je kunt deze map als stack in Portainer deployen. Alleen de volume en env-vars hoeven daarna nog aangepast te worden.

## Past bij jouw wens

- unlogged: iedereen ziet het dashboard
- logged in: invoeren en verwijderen
- dagoverzicht + overlay per dag
- werkt goed op mobiel
