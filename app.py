import os
from dotenv import load_dotenv
import streamlit as st

from src.data import load_data, read_uploaded_csv
from src.classify import classify_tweets
from src.locations import extract_locations
from src.geocode import geocode_locations
from src.map_view import create_map
from src.rag import semantic_search, summarize_reports

load_dotenv()


def main():
    st.set_page_config(page_title="Living Flood Map", layout="wide")
    st.title("Living Flood Map — Thunder Bay AI Hackathon")

    st.sidebar.header("Data")
    uploaded = st.sidebar.file_uploader("Upload CSV (must contain a 'tweet' column)")

    if uploaded is not None:
        df = read_uploaded_csv(uploaded)
    else:
        df = load_data()

    st.sidebar.markdown("---")
    st.sidebar.markdown("Pipeline (scaffold)")

    st.header("Dataset sample")
    st.write(df.head())

    if st.button("Classify tweets"):
        labeled = classify_tweets(df)
        st.write(labeled["label"].value_counts())
        st.dataframe(labeled.head())

    if st.button("Extract locations (scaffold)"):
        samples = df["tweet"].astype(str).tolist()[:200]
        locations = extract_locations(samples)
        st.write(f"Found {len(locations)} location mentions (first 50):")
        st.write(locations[:50])

    if st.button("Geocode locations (scaffold)"):
        samples = df["tweet"].astype(str).tolist()[:200]
        locations = extract_locations(samples)
        geocoded = geocode_locations(locations)
        if geocoded:
            m = create_map(geocoded)
            try:
                from streamlit_folium import st_folium

                st_folium(m, width=700)
            except Exception:
                st.write("Map created — install streamlit-folium to view in Streamlit.")
        else:
            st.write("No geocoded points returned.")


if __name__ == "__main__":
    main()
