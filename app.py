# app.py — Interface principale PGB Prospecting

import streamlit as st
import pandas as pd
from icp import generate_icp
from prospecting import search_prospects

st.set_page_config(
    page_title="PGB Prospecting",
    page_icon="🎯",
    layout="wide"
)

# --- Injection CSS — identité visuelle PGB ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Header principal */
h1 {
    font-size: 2.8rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    color: #000000 !important;
    margin-bottom: 0 !important;
}

/* Sous-titre caption */
.caption-pgb {
    font-size: 0.85rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #787878;
    margin-top: 0.25rem;
    margin-bottom: 2rem;
}

/* Labels de section */
h3 {
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    color: #787878 !important;
    margin-bottom: 0.75rem !important;
}

/* Bouton principal — Ink + Acid Lime */
.stButton > button[kind="primary"] {
    background-color: #000000 !important;
    color: #D0F028 !important;
    border: none !important;
    border-radius: 0px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    padding: 0.75rem 2rem !important;
    transition: background 0.15s ease !important;
}
.stButton > button[kind="primary"]:hover {
    background-color: #404040 !important;
    color: #D0F028 !important;
}

/* Formulaire — fond Paper légèrement contrasté */
[data-testid="stForm"] {
    background-color: #ffffff;
    border: 1px solid #C8C8C8;
    border-radius: 0px;
    padding: 2rem;
}

/* Inputs */
.stTextArea textarea, .stSelectbox select {
    border-radius: 0px !important;
    border-color: #B0B0B0 !important;
    font-family: 'Inter', sans-serif !important;
}

/* Info box — angle d'approche */
.stAlert {
    background-color: #000000 !important;
    color: #D0F028 !important;
    border-radius: 0px !important;
    border: none !important;
}
.stAlert p, .stAlert div {
    color: #D0F028 !important;
}

/* Divider */
hr {
    border-color: #C8C8C8 !important;
}

/* Tableau prospects */
[data-testid="stDataFrame"] {
    border: 1px solid #C8C8C8;
}

/* Bouton export */
.stDownloadButton > button {
    background-color: #F0F0F0 !important;
    color: #000000 !important;
    border: 1px solid #000000 !important;
    border-radius: 0px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
}
.stDownloadButton > button:hover {
    background-color: #000000 !important;
    color: #D0F028 !important;
}

/* Metric labels */
[data-testid="metric-container"] label {
    font-size: 0.7rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: #787878 !important;
}
</style>
""", unsafe_allow_html=True)


# --- Header ---
st.markdown("# BUREAU. Prospecting")
st.markdown('<p class="caption-pgb">Fiche produit &rarr; ICP &rarr; Prospects qualifiés</p>', unsafe_allow_html=True)
st.divider()

# --- Formulaire ---
with st.form("product_form"):
    product_description = st.text_area(
        "Décris ton service",
        placeholder="Ex: Audit d'entreprise 100% IA — analyse complète des processus internes, "
                    "identification des gains d'efficacité, livrable en 2 semaines.",
        height=160
    )

    col1, col2 = st.columns(2)
    with col1:
        country = st.selectbox(
            "Pays cible",
            ["France", "Belgique", "Suisse", "Luxembourg"],
            index=0
        )
    with col2:
        num_results = st.slider(
            "Nombre de prospects",
            min_value=5,
            max_value=25,
            value=15,
            step=5
        )

    submitted = st.form_submit_button(
        "Générer ICP + Prospects →",
        type="primary",
        use_container_width=True
    )

# --- Traitement ---
if submitted:
    if not product_description.strip():
        st.error("Décris ton service avant de lancer la recherche.")
        st.stop()

    # Étape 1 : Génération de l'ICP
    with st.spinner("Génération de l'ICP..."):
        try:
            icp = generate_icp(product_description)
        except Exception as e:
            st.error(f"Erreur ICP : {e}")
            st.stop()

    # Affichage ICP
    st.markdown("### ICP Généré")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**Secteurs**")
        for s in icp.get("sectors", []):
            st.markdown(f"&mdash; {s}")

    with c2:
        st.markdown("**Postes**")
        for j in icp.get("job_titles", []):
            st.markdown(f"&mdash; {j}")

    with c3:
        st.markdown("**Signaux d'achat**")
        for sig in icp.get("intent_signals", []):
            st.markdown(f"&mdash; {sig}")

    if icp.get("outreach_angle"):
        st.info(f"🎯 **Angle d'approche —** {icp['outreach_angle']}")

    st.divider()

    # Étape 2 : Recherche de prospects
    with st.spinner(f"Sourcing prospects — {country}..."):
        try:
            prospects = search_prospects(icp, country=country, num_results=num_results)
        except Exception as e:
            st.error(f"Erreur sourcing : {e}")
            st.stop()

    if not prospects:
        st.warning("Aucun prospect trouvé. Élargis les critères ICP.")
        st.stop()

    st.markdown(f"### {len(prospects)} Prospects")
    df = pd.DataFrame(prospects)
    st.dataframe(df, use_container_width=True, hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Exporter CSV",
        data=csv,
        file_name=f"prospects_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
