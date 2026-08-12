import base64

import streamlit as st

from jobmatch import config
from jobmatch.storage import read_json
from jobmatch.pipeline.state import load_status
from jobmatch.cv.generator import generate_cv


@st.cache_data
def get_base64_image(path):
    with open(path, "rb") as image:
        return base64.b64encode(image.read()).decode("utf-8")


def load_css():

    background_image = (
        get_base64_image(
            "assets/image1.png"
        )
    )

    with open(
        "assets/style.css",
        "r",
        encoding="utf-8"
    ) as css_file:

        css = css_file.read()

        css = css.replace(
            "{BACKGROUND_IMAGE}",
            background_image
        )

        st.markdown(
            f"<style>{css}</style>",
            unsafe_allow_html=True
        )

# Los tres ayudantes base64 eran idénticos; ahora hay uno solo (cacheado).
get_base64_logo = get_base64_image
get_base64_icon = get_base64_image

def render_header():

    logo = get_base64_logo(
        "assets/logo.png"
    )

    st.html(
        f"""
        <div class="hero-header">

            <img
                src="data:image/png;base64,{logo}"
                class="hero-logo"
            >

            <div>

                <div class="hero-title">
                    Career Radar
                </div>

                <div class="hero-subtitle">
                    AI-Powered Job Discovery & Resume Tailoring
                </div>

            </div>

        </div>
        """
    )


st.set_page_config(
    page_title="Career Radar",
    page_icon="📊",
    layout="wide"
)

load_css()

render_header()

st.divider()


def load_latest_jobs():
    return read_json(config.LATEST_JOBS_FILE, default=[])


jobs = load_latest_jobs()
status = load_status()

provider = (
    status["provider"]
    .lower()
)

engine_label = (
    "Gemini 2.5 Flash"
    if provider == "gemini"
    else status["provider"]
)

status_icon = {

    "Success": "✓",
    "Running": "⟳",
    "Error": "⚠",
    "Not executed": "○"

}.get(
    status["status"],
    "○"
)
suitcase_icon = get_base64_icon(
    "assets/icons/suitcase.png"
)

gemini_icon = get_base64_icon(
    "assets/icons/gemini.png"
)

ai_icon = get_base64_icon(
    "assets/icons/ai.png"
)
col1, col2, col3 = st.columns(3)

with col1:

    st.html(
        f"""
        <div class="top-card">

            <div class="top-card-content">

                <div class="top-card-icon">

                    <img
                        src="data:image/png;base64,{suitcase_icon}"
                        class="top-card-image-large"
                    >

                </div>

                <div class="top-card-text">

                    <div class="top-card-value">
                        {len(jobs)}
                    </div>

                    <div class="top-card-subtitle">
                        New Opportunities
                    </div>

                </div>

            </div>

        </div>
        """
    )
engine_icon = gemini_icon

with col2:

    st.html(
        f"""
        <div class="top-card">

            <div class="top-card-content">

                <div class="top-card-icon">

                    <img
                        src="data:image/png;base64,{engine_icon}"
                        class="top-card-image"
                    >

                </div>

                <div class="top-card-text">

                    <div class="top-card-value">
                        {engine_label}
                    </div>

                    <div class="top-card-subtitle">
                        AI Engine
                    </div>

                </div>

            </div>

        </div>
        """
    )

with col3:

    st.html(
        f"""
        <div class="top-card">

            <div class="top-card-content">

                <div class="top-card-icon">
                    ✓
                </div>

                <div class="top-card-text">

                    <div class="top-card-value">
                        {status['status']}
                    </div>

                    <div class="top-card-subtitle">
                        System Status
                    </div>

                </div>

            </div>

        </div>
        """
    )

jobs = sorted(
    jobs,
    key=lambda x: x["final_score"],
    reverse=True
)

def get_grade(score):
    if score >= 90:
        return "A+"
    elif score >= 80:
        return "A"
    elif score >= 60:
        return "B"
    elif score >= 40:
        return "C"
    return "D"


grade_counts = {
    "A+": 0,
    "A": 0,
    "B": 0,
    "C": 0,
    "D": 0
}

# Conteo global por score
for job in jobs:
    grade = get_grade(job["final_score"])
    grade_counts[grade] += 1

# Solo se mostrarán A+/A/B/C
visible_jobs = [
    job for job in jobs
    if job.get("final_score", 0) >= 40
]

# ==========================================================
# Source Quality
# ==========================================================
source_order = [
    "indeed",
    "occ",
    "linkedin",
    "computrabajo"
]

source_labels = {
    "indeed": "Indeed",
    "occ": "OCC",
    "linkedin": "LinkedIn",
    "computrabajo": "Computrabajo"
}

source_colors = {
    "indeed": "#7dd3fc",        # cyan
    "occ": "#a78bfa",           # violet
    "linkedin": "#60a5fa",      # blue
    "computrabajo": "#34d399"   # emerald
}

source_stats = {
    source: {
        "total": 0,
        "score_sum": 0,
        "avg_score": 0,
        "A+": 0,
        "A": 0,
        "B": 0,
        "C": 0,
        "D": 0
    }
    for source in source_order
}

# 1) Llenar estadísticas por fuente
for job in jobs:
    job_data = job.get("job", {})
    source = str(job_data.get("source", "")).strip().lower()
    score = job.get("final_score", 0)
    grade = get_grade(score)

    if source not in source_stats:
        source_stats[source] = {
            "total": 0,
            "score_sum": 0,
            "avg_score": 0,
            "A+": 0,
            "A": 0,
            "B": 0,
            "C": 0,
            "D": 0
        }
        source_labels[source] = source.title()
        source_colors[source] = "#94a3b8"

    source_stats[source]["total"] += 1
    source_stats[source]["score_sum"] += score
    source_stats[source][grade] += 1

# 2) Calcular promedio por fuente
for source, stats in source_stats.items():
    if stats["total"] > 0:
        stats["avg_score"] = stats["score_sum"] / stats["total"]
    else:
        stats["avg_score"] = 0

# 3) Ordenar fuentes por calidad promedio
ordered_sources = sorted(
    [s for s in source_stats.keys() if source_stats[s]["total"] > 0],
    key=lambda s: source_stats[s]["avg_score"],
    reverse=True
)

grade_color = {

    "A+": "🟢",
    "A": "🔵",
    "B": "🟡",
    "C": "🟠",
    "D": "🔴"
}


grade_ranges = {

    "A+": "90-100",
    "A": "80-89",
    "B": "60-79",
    "C": "40-59",
    "D": "0-39"
}
source_quality_html = ""
max_source_total = max(
    [stats["total"] for stats in source_stats.values()] or [1]
)

for source in ordered_sources:
    if source not in source_stats:
        continue

    stats = source_stats[source]
    total = stats["total"]

    if total == 0:
        continue

    lollipop_width = (total / max_source_total) * 100
    label = source_labels.get(source, source.title())
    dot_color = source_colors.get(source, "#94a3b8")

    breakdown_html = ""
    for grade in ["A+", "A", "B", "C", "D"]:
        count = stats[grade]
        if count == 0:
            continue

        breakdown_html += f"""
        <span class="source-grade-pill source-grade-{grade.replace('+', 'plus')}">
            {grade} {count}
        </span>
        """

    source_quality_html += f"""
    <div class="source-quality-item">

        <div class="source-quality-header">
            <div class="source-quality-name">{label}</div>
            <div class="source-quality-total">{total}</div>
        </div>

        <div class="source-lollipop-row">
            <div class="source-lollipop-track">
                <div
                    class="source-lollipop-line"
                    style="
                        width:{lollipop_width}%;
                        background:linear-gradient(90deg, rgba(255,255,255,0.16) 0%, {dot_color} 100%);
                    "
                ></div>

                <div
                    class="source-lollipop-dot"
                    style="
                        left:calc({lollipop_width}% - 10px);
                        background:{dot_color};
                        box-shadow:0 0 14px {dot_color};
                    "
                ></div>
            </div>
        </div>

        <div class="source-breakdown-row">
            {breakdown_html}
        </div>

    </div>
    """
with st.sidebar:

    grades_html = ""

    max_count = max(
    grade_counts.values()
)

    for grade, count in grade_counts.items():

        bar_width = (
            count / max_count
        ) * 100 if max_count > 0 else 0

        bar_gradients = {

            "A+": "linear-gradient(90deg, #f2f2f2 0%, #d9ffe9 18%, #b7ffd7 35%, #7dffb3 60%, #7dffb3 100%)",

            "A": "linear-gradient(90deg, #f2f2f2 0%, #dbe9ff 18%, #bcd8ff 35%, #60a5fa 60%, #60a5fa 100%)",

            "B": "linear-gradient(90deg, #f2f2f2 0%, #fff5c7 18%, #fff1a8 35%, #facc15 60%, #facc15 100%)",

            "C": "linear-gradient(90deg, #f2f2f2 0%, #ffe0c8 18%, #ffd1ab 35%, #fb923c 60%, #fb923c 100%)",

            "D": "linear-gradient(90deg, #f2f2f2 0%, #ffd8d8 18%, #ffc0c0 35%, #f87171 60%, #f87171 100%)"
        }

        grades_html += f"""
        <div class="sidebar-grade-row">

            <div class="sidebar-grade-label">
                {grade_color[grade]}
                {grade} ({grade_ranges[grade]})
            </div>

            <div class="sidebar-grade-bar">

                <div
                    class="sidebar-grade-fill"
                    style="
                        width:{bar_width}%;
                        background:{bar_gradients[grade]};
                    "
                ></div>

            </div>

            <div class="sidebar-grade-count">
                {count}
            </div>

        </div>
        """

    st.html(
        f"""
        <div class="sidebar-card">

            <div class="sidebar-title">
                System Status
            </div>

            <div class="sidebar-item">
                {status_icon}
                {status['status']}
            </div>

            <div class="sidebar-divider"></div>

            <div class="sidebar-item">
                Provider:
                {status['provider']}
            </div>

            <div class="sidebar-divider"></div>

            <div class="sidebar-item">
                📊 Jobs Processed:
                {status['jobs_processed']}
            </div>

            <div class="sidebar-divider"></div>

            <div class="sidebar-item">
                🕒 Last Run:
            </div>

            <div class="sidebar-item">
                {status['last_run']}
            </div>

            <div class="sidebar-message">
                ✓ {status['message']}
            </div>

        </div>

        <div class="sidebar-card">

            <div class="sidebar-title">
                Job Summary
            </div>

            <div class="sidebar-inline-stats">
                <div class="sidebar-inline-stat">
                    <span class="sidebar-inline-label">Loaded</span>
                    <span class="sidebar-inline-value">{len(jobs)}</span>
                </div>

                <div class="sidebar-inline-separator"></div>

                <div class="sidebar-inline-stat">
                    <span class="sidebar-inline-label">Visible</span>
                    <span class="sidebar-inline-value">{len(visible_jobs)}</span>
                </div>
            </div>

            <div class="sidebar-section-divider"></div>

            {grades_html}

        </div>

        <div class="sidebar-card">

            <div class="sidebar-title">
                Source Quality
            </div>

            {source_quality_html}

        </div>
        """
    )


st.subheader(
    "Ranked Opportunities"
)

for job in visible_jobs:

    score = job["final_score"]
    grade = get_grade(score)

    with st.expander(


        f"{grade_color[grade]} "
        f"{grade} | "
        f"{score} pts | "
        f"{job['title']}"

    ):
        job_data = job.get(
            "job",
            {}
        )

        remote_text = (
            "Remote"
            if job_data.get("remote")
            else "On Site"
        )

        grade_style = {

            "A+": (
                "#7dffb3",
                "rgba(125,255,179,0.08)",
                "rgba(125,255,179,0.25)"
            ),

            "A": (
                "#60a5fa",
                "rgba(96,165,250,0.08)",
                "rgba(96,165,250,0.25)"
            ),

            "B": (
                "#facc15",
                "rgba(250,204,21,0.08)",
                "rgba(250,204,21,0.25)"
            ),

            "C": (
                "#fb923c",
                "rgba(251,146,60,0.08)",
                "rgba(251,146,60,0.25)"
            ),

            "D": (
                "#f87171",
                "rgba(248,113,113,0.08)",
                "rgba(248,113,113,0.25)"
            )

        }

        grade_text_color, grade_bg, grade_border = (
            grade_style[grade]
        )

        st.html(
            f"""
            <div class="job-header">

                <div
                    class="job-grade-box"
                    style="
                        color:{grade_text_color};
                        background:{grade_bg};
                        border:1px solid {grade_border};
                    "
                >
                    {grade}
                </div>

                <div class="job-score-box">
                    {score}
                </div>

                <div class="job-header-info">

                    <div class="job-header-title">
                        {job['title']}
                    </div>

                    <div class="job-header-meta">

                        {job['company']}
                        •
                        {job_data.get('source', '').upper()}
                        •
                        <span class="job-remote">
                            {remote_text}
                        </span>
                        •
                        {job_data.get('days_old')} days old

                    </div>

                </div>

            </div>
            """
        )
        
        col1, col2, col3 = st.columns(3)

        with col1:

            st.html(
                f"""
                <div class="score-card">

                    <div class="score-content">

                        <div class="score-icon">
                            🏆
                        </div>

                        <div class="score-text">

                            <div class="score-value">
                                {score}
                            </div>

                            <div class="score-label">
                                Final Score
                            </div>

                        </div>

                    </div>

                </div>
                """
            )

        with col2:

            st.html(
                f"""
                <div class="score-card">

                    <div class="score-content">

                        <div class="score-icon">
                            🎯
                        </div>

                        <div class="score-text">

                            <div class="score-value">
                                {job.get('matcher_score', '-')}
                            </div>

                            <div class="score-label">
                                Matcher Score
                            </div>

                        </div>

                    </div>

                </div>
                """
            )

        with col3:

            icon = "✦"
            label = "Gemini Score"

            st.html(
                f"""
                <div class="score-card">

                    <div class="score-content">

                        <div class="score-icon">
                            {icon}
                        </div>

                        <div class="score-text">

                            <div class="score-value">
                                {job.get('gemini_score', '-')}
                            </div>

                            <div class="score-label">
                                {label}
                            </div>

                        </div>

                    </div>

                </div>
                """
            )

        st.divider()

        st.subheader(
            "🧠 AI Summary"
        )

        summary = job.get(
            "summary",
            ""
        )

        if summary:

            st.info(
                summary
            )

        else:

            st.warning(
                "Pending AI analysis"
            )

        pros = job.get(
            "pros",
            []
        )

        contras = job.get(
            "contras",
            []
        )

        st.divider()

        col_pros, col_divider, col_cons = st.columns(
            [1, 0.05, 1]
        )

        with col_pros:

            st.subheader(
                "📈 Pros"
            )

            if pros:

                for pro in pros:

                    st.write(
                        f"✅ {pro}"
                    )

            else:

                st.write(
                    "No pros available."
                )
        with col_divider:

            st.html(
                """
                <div class="pros-cons-divider"></div>
                """
            )

        with col_cons:

            st.subheader(
                "⚠️ Cons"
            )

            if contras:

                for contra in contras:

                    st.write(
                        f"❌ {contra}"
                    )

            else:

                st.write(
                    "No cons available."
                )

        st.divider()

        st.subheader(
            "📋 Job Details"
        )

        remote_value = job_data.get(
            "remote"
        )

        remote_icon = (
            "✅"
            if remote_value
            else "❌"
        )

        col_info_1, col_info_2 = st.columns(2)

        with col_info_1:

            st.html(
                f"""
                <div class="job-detail-item">

                    <span class="job-detail-label">
                        Remote
                    </span>

                     <span class="job-detail-badge">
                        {remote_icon}
                        {remote_value}
                    </span>

                </div>
                """
            )

        with col_info_2:

            st.html(
                f"""
                <div class="job-detail-item">

                    <span class="job-detail-label">
                        Days Old
                    </span>

                    <span class="job-detail-badge">
                        {job_data.get('days_old')}
                        days
                    </span>

                 </div>
                """
            )

        st.write("")

        col_a, col_b = st.columns(2)
        pdf_key = f"generated_pdf::{job['url']}"

        with col_a:

            st.link_button(
                "Open Job",
                job["url"],
                use_container_width=True
            )

        with col_b:

            generate_cv_clicked = st.button(
                "Generate CV",
                key=f"cv_{job['url']}",
                use_container_width=True
            )

            if generate_cv_clicked:

                with st.spinner(
                     "Generating CV..."
                ):

                     output_file = generate_cv(
                        job
                    )

                st.session_state[pdf_key] = output_file

                st.success(
                    "CV generated successfully."
                )

        if pdf_key in st.session_state:

            st.divider()

            st.subheader(
                "CV Preview"
            )

            pdf_path = st.session_state[pdf_key]

            with open(
                pdf_path,
                "rb"
            ) as pdf_file:

                base64_pdf = (
                    base64.b64encode(
                        pdf_file.read()
                    )
                    .decode(
                        "utf-8"
                    )
                )

            pdf_display = f"""
            <iframe
                src="data:application/pdf;base64,{base64_pdf}"
                width="100%"
                height="900"
                type="application/pdf">
            </iframe>
            """

            st.markdown(
                pdf_display,
                unsafe_allow_html=True
            )