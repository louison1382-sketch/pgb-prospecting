# app.py — Interface principale PGB Prospecting
#
# Lance avec : streamlit run app.py
# L'app s'ouvre dans le navigateur sur http://localhost:8501

import streamlit as st
import pandas as pd
from icp import generate_icp
from prospecting import search_prospects

# --- Configuration de la page ---
st.set_page_config(
    page_title="PGB Prospecting",
    page_icon="🎯",
    layout="wide"
)

# --- Header ---
st.title("PGB Prospecting")
st.caption("Génère un ICP et une liste de prospects qualifiés à partir de ta fiche produit.")
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

    submitted = st.form_submit_button("Générer ICP + Prospects →", type="primary", use_container_width=True)

# --- Traitement ---
if submitted:
    if not product_description.strip():
        st.error("Décris ton service avant de lancer la recherche.")
        st.stop()

    # Étape 1 : Génération de l'ICP
    with st.spinner("Génération de l'ICP en cours..."):
        try:
            icp = generate_icp(product_description)
        except Exception as e:
            st.error(f"Erreur lors de la génération de l'ICP : {e}")
            st.stop()

    # Affichage de l'ICP
    st.subheader("ICP Généré")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**Secteurs cibles**")
        for s in icp.get("sectors", []):
            st.markdown(f"- {s}")

    with c2:
        st.markdown("**Postes ciblés**")
        for j in icp.get("job_titles", []):
            st.markdown(f"- {j}")

    with c3:
        st.markdown("**Signaux d'achat**")
        for sig in icp.get("intent_signals", []):
            st.markdown(f"- {sig}")

    if icp.get("outreach_angle"):
        st.info(f"**Angle d'approche :** {icp['outreach_angle']}")

    st.divider()

    # Étape 2 : Recherche de prospects
    with st.spinner(f"Recherche de prospects en {country}..."):
        try:
            prospects = search_prospects(icp, country=country, num_results=num_results)
        except Exception as e:
            st.error(f"Erreur lors de la recherche : {e}")
            st.stop()

    if not prospects:
        st.warning("Aucun prospect trouvé avec ces critères. Essaie d'élargir les filtres.")
        st.stop()

    # Affichage des résultats
    st.subheader(f"{len(prospects)} prospects trouvés")
    df = pd.DataFrame(prospects)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Export CSV
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Exporter en CSV",
        data=csv,
        file_name=f"prospects_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
