import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

DB = Path(__file__).parent / "kino.db"

ZAPYT = """
SELECT f.id, f.title, f.year, f.director, f.duration_min,
       COUNT(v.id) AS pereglyadiv,
       SUM(v.viewers) AS glyadachiv,
       (SELECT COUNT(*) FROM cast_members AS c WHERE c.film_id = f.id) AS cast_count
FROM films AS f
JOIN views AS v ON v.film_id = f.id
WHERE f.year BETWEEN ? AND ?
  AND v.viewed_on BETWEEN ? AND ?
  AND (? IS NULL OR f.director = ?)
  AND (? = 0 OR f.duration_min >= ?)
GROUP BY f.id
ORDER BY glyadachiv DESC, f.id
"""


@st.cache_data
def chytaty(rik_vid, rik_do, data_vid, data_do, director, tryvalist):
    with closing(sqlite3.connect(DB)) as conn:
        return pd.read_sql_query(
            ZAPYT,
            conn,
            params=(
                rik_vid, rik_do, data_vid, data_do,
                director, director, tryvalist, tryvalist,
            ),
        )


with closing(sqlite3.connect(DB)) as conn:
    films = conn.execute(
        "SELECT id, title, year FROM films ORDER BY title, year, id"
    ).fetchall()
    directors = [
        row[0] for row in conn.execute(
            "SELECT DISTINCT director FROM films ORDER BY director"
        )
    ]
    max_duration = int(conn.execute(
        "SELECT COALESCE(MAX(duration_min), 1) FROM films"
    ).fetchone()[0])

film_labels = {
    film_id: f"{title} ({year})" for film_id, title, year in films
}

st.title("Кінопанель · PY-C2P")

first_date = date(2024, 1, 1)
last_date = date(2025, 12, 31)

with st.sidebar:
    rik_vid, rik_do = st.slider("Роки випуску", 1920, 2020, (1930, 1969))
    dates = st.date_input(
        "Дати переглядів",
        value=(first_date, last_date),
        min_value=first_date,
        max_value=last_date,
    )
    director = st.selectbox(
        "Режисер",
        [None, *directors],
        format_func=lambda name: "Усі режисери" if name is None else name,
    )
    tryvalist = st.slider("Мінімальна тривалість, хв", 0, max_duration, 0)

with st.expander("Додати актора до фільму"):
    with st.form("cast_form"):
        film_id = st.selectbox(
            "Фільм", list(film_labels), format_func=film_labels.get
        )
        actor = st.text_input("Ім’я актора")
        role_name = st.text_input("Назва ролі")
        is_lead = st.checkbox("Головна роль")
        submitted = st.form_submit_button("Зберегти")

    if submitted:
        if not actor.strip() or not role_name.strip():
            st.error("Заповни ім’я актора й назву ролі.")
        else:
            with closing(sqlite3.connect(DB)) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                with conn:
                    conn.execute(
                        """
                        INSERT INTO cast_members (film_id, actor, role_name, is_lead)
                        VALUES (?, ?, ?, ?)
                        """,
                        (film_id, actor.strip(), role_name.strip(), int(is_lead)),
                    )

            st.session_state["cast_added"] = st.session_state.get("cast_added", 0) + 1
            chytaty.clear()
            st.success("Запис збережено.")

    st.write("Додано за цю сесію:", st.session_state.get("cast_added", 0))

if len(dates) != 2:
    st.info("Обери початкову й кінцеву дати переглядів.")
    st.stop()

df = chytaty(
    rik_vid, rik_do, dates[0].isoformat(), dates[1].isoformat(),
    director, tryvalist,
)

import plotly.express as px

st.metric("Записів акторського складу", int(df["cast_count"].sum()))

tab_data, tab_charts = st.tabs(["Дані", "Графіки"])

with tab_data:
    if df.empty:
        st.info("За цими фільтрами фільмів не знайдено.")
    else:
        st.dataframe(df.drop(columns="id"), hide_index=True, width="stretch")

with tab_charts:
    if df.empty:
        st.info("За цими фільтрами немає даних для графіків.")
    else:
        left, right = st.columns(2)

        with left:
            st.subheader("Топ-10 фільмів за акторським складом")
            top_cast = df.sort_values(
                ["cast_count", "title"], ascending=[False, True]
            ).head(10).copy()
            top_cast["film_label"] = (
                top_cast["title"] + " (" + top_cast["year"].astype(str) + ")"
            )
            st.bar_chart(
                top_cast,
                x="film_label",
                y="cast_count",
                x_label="Фільм",
                y_label="Записів акторського складу",
                horizontal=True,
            )

        with right:
            st.subheader("Рік випуску та кількість глядачів")
            fig = px.scatter(
                df,
                x="year",
                y="glyadachiv",
                hover_name="title",
                labels={"year": "Рік випуску", "glyadachiv": "Усього глядачів"},
            )
            st.plotly_chart(fig, width="stretch")
