import streamlit as st
import requests
import urllib.parse
import pandas as pd
from fpdf import FPDF
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv
import os

load_dotenv()

# ========== API KEYS ==========
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")


# ========== FUNCTIONS ==========
@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/USD"
        data = requests.get(url).json()
        if data.get('result') == 'success':
            return data['conversion_rates']['INR']
        
    except:
        pass
    return None

def convert_usd_to_inr(box_office_str, exchange_rate):
    if box_office_str in [None, 'N/A'] or exchange_rate is None:
        return 'N/A'
    
    try:
        amount_usd = float(box_office_str.replace('$', '').replace(',', '').strip())
        amount_inr = amount_usd * exchange_rate
        return f"₹{amount_inr:,.0f}"
    
    except:
        return box_office_str

def get_movie_info(movie_name, exchange_rate):
    encoded_movie_name = urllib.parse.quote(movie_name)
    url = f"http://www.omdbapi.com/?t={encoded_movie_name}&apikey={OMDB_API_KEY}&plot=full"
    data = requests.get(url).json()

    if data.get('Response') == 'True':
        country = (data.get('Country') or '').lower()
        language = (data.get('Language') or '').lower()

        if 'india' in country or 'hindi' in language:
            actors = data.get('Actors', 'N/A')
            director = data.get('Director', 'N/A')
            release_date = data.get('Released', 'N/A')
            imdb_rating = data.get('imdbRating', 'N/A')
            plot = data.get('Plot', 'No plot available')
            box_office_usd = data.get('BoxOffice', 'N/A')
            poster_url = data.get('Poster', None)

            box_office_inr = convert_usd_to_inr(box_office_usd, exchange_rate)

            try:
                rating = float(imdb_rating)
                hit_status = "Hit" if rating >= 7 else "Flop"

            except:
                hit_status = "Rating not available"

            return {
                "Title": data.get('Title', movie_name),
                "Director": director,
                "Actors": actors,
                "Release Date": release_date,
                "IMDb Rating": imdb_rating,
                "Box Office (INR)": box_office_inr,
                "Hit Status": hit_status,
                "Poster": poster_url,
                "Plot": plot
            }
        else:
            return {"error": "Not a Bollywood movie."}
    else:
        return {"error": f"Movie '{movie_name}' not found."}

# PDF safe string helper
def pdf_safe(value) -> str:
    s = "" if value is None else str(value)
    s = s.replace("₹", "Rs. ")
    return s.encode("latin-1", errors="replace").decode("latin-1")

# Create PDF with poster and actors on separate lines
def create_pdf(df: pd.DataFrame) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, pdf_safe("Bollywood Movie Info"), ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", "", 11)

    for idx, row in df.iterrows():
        # Add poster if available
        poster_url = row.get("Poster")
        if poster_url and poster_url != "N/A":
            try:
                response = requests.get(poster_url)
                image = Image.open(BytesIO(response.content))
                image_path = f"temp_image_{idx}.png"
                image.save(image_path)
                pdf.image(image_path, w=50)
                pdf.ln(5)

            except:
                pass

        for col, val in row.items():
            if col == "Actors" and val != "N/A":
                pdf.multi_cell(0, 8, "Actors:")
                actors_list = val.split(",")
                for actor in actors_list:
                    pdf.multi_cell(0, 8, f"- {pdf_safe(actor.strip())}")
            elif col not in ["Poster", "Plot"]:
                line = f"{col}: {pdf_safe(val)}"
                pdf.multi_cell(0, 8, line)
        pdf.ln(5)

    return pdf.output(dest="S").encode("latin-1", errors="replace")

# ========== MAIN APP ==========
def main():
    st.set_page_config(page_title="Bollywood Movie Info", layout="wide")
    st.title("Bollywood Movie Info App")
    st.caption("Get detailed info on Bollywood movies with posters, ratings, and box office earnings.")

    if 'movies' not in st.session_state:
        st.session_state.movies = []
    if 'selected_movie' not in st.session_state:
        st.session_state.selected_movie = None
    if 'df' not in st.session_state:
        st.session_state.df = pd.DataFrame(columns=["Title", "Director", "Actors", "Release Date", "IMDb Rating", "Box Office (INR)", "Hit Status", "Poster"])

    exchange_rate = get_exchange_rate()
    if exchange_rate is None:
        st.warning("Live USD to INR rate unavailable.")

    # Sidebar recent searches
    st.sidebar.header("Recent Searches")
    for idx, movie in enumerate(st.session_state.movies[-5:]):
        if st.sidebar.button(movie.get('Title', f'Movie {idx}'), key=f"history_{idx}"):
            st.session_state.selected_movie = movie
        if movie.get("Poster") and movie["Poster"] != "N/A":
            st.sidebar.image(movie["Poster"], width=80)

    movie_name = st.text_input("Enter movie name")

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("Get Movie Info"):
            if movie_name.strip():
                with st.spinner("Fetching..."):
                    info = get_movie_info(movie_name.strip(), exchange_rate)
                if "error" in info:
                    st.error(info["error"])
                else:
                    st.session_state.movies.append(info)
                    st.session_state.selected_movie = info
                    st.session_state.df = pd.DataFrame(st.session_state.movies)
                    st.success(f"Added '{info['Title']}'")
            else:
                st.error("Please enter a movie name.")

    with col2:
        if st.button("Clear All"):
            st.session_state.movies.clear()
            st.session_state.selected_movie = None
            st.session_state.df = pd.DataFrame(columns=st.session_state.df.columns)
            st.success("Cleared all.")

    # Display selected movie
    if st.session_state.selected_movie:
        movie = st.session_state.selected_movie
        st.subheader(movie['Title'])
        if movie.get('Poster') and movie['Poster'] != 'N/A':
            st.image(movie['Poster'], width=300)
        st.write(f"**Director:** {movie['Director']}")

        # Show each actor as bullet point
        st.write("**Actors:**")
        actors_list = movie['Actors'].split(",") if movie['Actors'] != 'N/A' else []
        for actor in actors_list:
            st.markdown(f"- {actor.strip()}")

        st.write(f"**Release Date:** {movie['Release Date']}")
        st.write(f"**IMDb Rating:** {movie['IMDb Rating']}")
        try:
            rating_val = float(movie['IMDb Rating'])
            st.progress(rating_val / 10)

        except:
            pass
        st.write(f"**Box Office (INR):** {movie['Box Office (INR)']}")
        st.write(f"**Hit Status:** {movie['Hit Status']}")
        with st.expander("About this movie"):
            st.write(movie['Plot'])

    # Display table and download options
    if not st.session_state.df.empty:
        st.subheader("Movie Summary")
        st.dataframe(st.session_state.df.style.highlight_max(subset=['IMDb Rating'], color='lightgreen'))

        csv = st.session_state.df.to_csv(index=False).encode('utf-8')
        pdf_bytes = create_pdf(st.session_state.df)

        colA, colB = st.columns(2)
        with colA:
            st.download_button("Download CSV", csv, "movies.csv", "text/csv")
            
        with colB:
            st.download_button("Download PDF", pdf_bytes, "movies.pdf", "application/pdf")

if __name__ == "__main__":
    main()
