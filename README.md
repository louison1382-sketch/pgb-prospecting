# PGB Prospecting

Moteur de prospection IA pour Pillet Grenié BUREAU.

**Ce que ça fait :** tu colles une description de service → l'outil génère un ICP (Ideal Customer Profile) via Claude, puis cherche des prospects correspondants avec leurs emails.

**Stack :** Python · Streamlit · Claude API · Apollo.io API

---

## Lancer l'app en 5 minutes (GitHub Codespaces)

1. Ouvre ce repo sur GitHub
2. Clique sur **Code → Codespaces → Create codespace on main**
3. Attends 30 secondes que l'environnement démarre
4. Dans le terminal qui s'ouvre, tape :

```bash
pip install -r requirements.txt
cp .env.example .env
```

5. Ouvre le fichier `.env` et remplis tes clés API (voir section ci-dessous)
6. Lance l'app :

```bash
streamlit run app.py
```

7. Clique sur le lien qui apparaît → l'app s'ouvre dans ton navigateur

---

## Clés API nécessaires

### 1. Anthropic (Claude)
- Va sur [console.anthropic.com](https://console.anthropic.com)
- Clique sur **API Keys → Create Key**
- Copie la clé dans `.env` : `ANTHROPIC_API_KEY=sk-ant-...`

### 2. Apollo.io (prospection)
- Va sur [app.apollo.io](https://app.apollo.io) → crée un compte gratuit
- Va dans **Settings → Integrations → API**
- Copie la clé dans `.env` : `APOLLO_API_KEY=...`
- Le tier gratuit donne 50 crédits/mois pour tester

---

## Déploiement (Railway)

Une fois que l'app tourne en local et que tu veux la mettre en ligne :

1. Va sur [railway.app](https://railway.app) → connecte ton GitHub
2. **New Project → Deploy from GitHub repo → pgb-prospecting**
3. Dans **Variables**, ajoute `ANTHROPIC_API_KEY` et `APOLLO_API_KEY`
4. Railway génère une URL publique automatiquement

---

## Architecture

```
app.py          → Interface Streamlit (formulaire + résultats)
icp.py          → Génération ICP via Claude API
prospecting.py  → Sourcing prospects via Apollo.io API
.env            → Clés API (jamais committé sur GitHub)
```
