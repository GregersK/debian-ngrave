# Testserver ved siden af LAASENGRAVE01

Den gamle server (**LAASENGRAVE01**) bliver stående og kører produktionen som
altid. Ved siden af laves en ny server (**LAASENGRAVE01-TEST**) med den nye
version og en kopi af dataene. Testserveren:

- **sender ikke til maskinerne.** Hvert job bliver i stedet gemt som en fil med
  præcis det program maskinen ville have fået. Det gælder også jobs der står i kø
  i kopien.
- **kontakter ikke maskinerne.** Den laver ikke online-tjek og kører ikke til
  test-positionen, så den forstyrrer aldrig den gamle server.
- **opdaterer ikke sig selv** til et release-tag.
- **viser et orange banner** "TESTSERVER" og sit navn i fanen, så de to servere
  ikke kan forveksles.

Først når du selv vælger det, må testserveren sende til **én bestemt maskine**
(trin 6).

---

## 1. Ny VM

I VMware:
- Lav en ny VM med Debian 12, som de andre servere.
- Giv den navnet `LAASENGRAVE01-TEST` og en IP på samme net som maskinerne.
- Testserveren skal **ikke** have DNS-navnet `ngrave.laas.local`. Det bliver på den
  gamle server. Brug den nye servers IP-adresse.

Sæt navnet på VM'en (som root i konsollen):

```bash
hostnamectl set-hostname LAASENGRAVE01-TEST
```

## 2. Installér den nye version som testserver

Som root på den nye server:

```bash
apt update && apt install -y curl
curl -fsSL https://raw.githubusercontent.com/GregersK/debian-ngrave/claude/code-review-q6onT/install.sh -o install.sh
NGRAVE_REF=claude/code-review-q6onT NGRAVE_TESTSERVER=1 NGRAVE_SERVERNAVN=LAASENGRAVE01-TEST bash install.sh
```

Installationen skriver et **nyt login** ud (`ngrave` / et genereret password). Gem
det. Det er et andet password end den gamle servers.

## 3. Kopiér data fra den gamle server

Kopien indeholder templates, skilt-templates, materialer, maskiner med
kalibrering og historik. Den gamle server **ændres ikke**: databasen læses med
SQLite's backup-funktion, som er sikker mens tjenesten kører.

**A) Har den nye server SSH-adgang som root til den gamle**, så kør dette på den
nye server:

```bash
bash /opt/ngrave/tools/kopier-fra-server.sh root@<IP på LAASENGRAVE01>
```

**B) Ellers** (Debian tillader som standard ikke root-login med password over
SSH):

1. Lav kopien på **den gamle server** i VMware-konsollen, som root:

   ```bash
   python3 -c "import sqlite3; s=sqlite3.connect('/opt/ngrave/ngrave.db'); d=sqlite3.connect('/tmp/ngrave-kopi.db'); s.backup(d); d.close(); print('ok')"
   chmod 644 /tmp/ngrave-kopi.db
   ```

2. Hent filen fra **den nye server**. Brug en almindelig bruger på den gamle
   server, ikke root:

   ```bash
   scp <bruger>@<IP på LAASENGRAVE01>:/tmp/ngrave-kopi.db /root/
   bash /opt/ngrave/tools/kopier-fra-server.sh --fil /root/ngrave-kopi.db LAASENGRAVE01
   ```

3. Slet kopien på den gamle server igen: `rm /tmp/ngrave-kopi.db`

Scriptet gør tre ting:
- **Opgraderer kopien** til den nye version.
- **Neutraliserer ventende jobs.** De sættes til "fejl" med teksten "Kopieret fra
  LAASENGRAVE01 — ikke sendt fra testserveren". Den gamle server har dem stadig.
- **Fortæller hvad der er kopieret.** Det nævner også hvor mange nøgle-templates
  der graverer i Block som i v6.1.

Scriptet kan køres igen senere for at få friske data. Testserverens forrige
database gemmes som `ngrave.db.foer-kopi-<dato>`.

## 4. Kig efter i browseren

Åbn `http://<IP på LAASENGRAVE01-TEST>`:

- **Øverst:** det orange banner "TESTSERVER", og fanen hedder
  "TEST · LAASENGRAVE01-TEST".
- **Nøgler → Templates:** alle jeres templates. Templates der havde valgt en anden
  skrifttype end Block, har mærket "Block som v6.1". De graverer præcis som før.
- **Nøgler → Materialer:** profilen "Messing", lavet ud fra jeres nuværende
  værdier. Opret "Akryl/plast" med jeres værdier.
- **System → Maskiner:** alle maskiner står som "Testserver: sender ikke".

## 5. Side om side: samme ordre på begge servere

Lav jeres almindelige ordrer på **den gamle** server, som I plejer. Lav **de
samme** ordrer på testserveren. De bliver ikke graveret; programmerne havner
under **System → Testserver: gemte programmer**, hvor de kan åbnes.

Sammenlign dem med det v6.1.1 ville have sendt. Kør dette på testserveren:

```bash
/opt/ngrave/venv/bin/python /opt/ngrave/tools/sammenlign_v611.py
```

Værktøjet bygger programmet igen med den rigtige v6.1.1-kode (fra git) ud fra
samme ordre, template og maskine:

- **`✓ IDENTISK`:** maskinen ville få præcis det samme. Det er det forventede for
  alle jeres eksisterende templates, så længe I ikke har slået nye funktioner til.
- **`≠ ÆNDRET`:** der står hvorfor, fx "templaten bruger et materiale", "maskinens
  optimering er «fuld»" eller "«Gravér alt i Block (som i v6.1)» er slået fra".

Skilte sammenlignes ikke. Den nye version har en ny layout-motor til skilte med
rettede margener og kant-tjek, så de er bevidst anderledes.

## 6. Rigtig gravering fra testserveren (én maskine ad gangen)

Når I vil prøve de nye ting på skrotmateriale (nye skrifttyper, ægte ÆØÅ,
materialer, optimering "Fuld", lavt løft mellem bogstaver):

1. **Vælg en maskine.** Find dens nummer (`#3` osv.) under System → Maskiner, og
   sørg for at **den gamle server ikke bruger maskinen imens**. En maskine kan
   kun modtage fra én ad gangen.
2. **Giv testserveren lov til at sende til den maskine.** På testserveren:

   ```bash
   sed -i 's/^NGRAVE_TEST_SEND_TIL=.*/NGRAVE_TEST_SEND_TIL=3/' /etc/ngrave/ngrave.env
   systemctl restart ngrave
   ```

   Banneret siger nu "undtagen maskine 3, som får rigtige jobs". Maskine 3 bliver
   online-tjekket og kan bruge test-positionen. Alle andre maskiner er stadig
   fredet.
3. **Lav testjob** på maskine 3, med de nye funktioner slået til én ad gangen.
4. **Slå det fra igen**, når I er færdige:

   ```bash
   sed -i 's/^NGRAVE_TEST_SEND_TIL=.*/NGRAVE_TEST_SEND_TIL=/' /etc/ngrave/ngrave.env
   systemctl restart ngrave
   ```

## 7. Ny version på testserveren

Testserveren opdaterer ikke sig selv. Hent den nyeste udgave af branchen:

```bash
cd /root && NGRAVE_REF=claude/code-review-q6onT NGRAVE_TESTSERVER=1 bash install.sh
```

Login, data og indstillinger bevares.

## 8. Når testen er overstået

Når alt er godkendt, tagges v6.2. Så opdaterer de rigtige servere sig selv, også
LAASENGRAVE01. Testserveren kan slettes eller beholdes som fast testmaskine.

---

**Hvis noget går galt på testserveren**, så stop den: `systemctl stop ngrave`.
Den gamle server er ikke påvirket af noget af det her.
