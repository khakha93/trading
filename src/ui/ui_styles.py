import streamlit as st


def inject_app_styles() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;600;700;800&display=swap');

            html, body, [class*="css"] {
                font-family: 'Inter', sans-serif;
            }

            .main-title {
                font-family: 'Outfit', sans-serif;
                background: linear-gradient(135deg, #00C6FF, #0072FF);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-weight: 800;
                font-size: 2.3rem;
                margin-bottom: 0.2rem;
            }

            .subtitle {
                color: #8888aa;
                font-size: 1rem;
                margin-bottom: 1.5rem;
            }

            .custom-card {
                background-color: #1E1E24;
                border: 1px solid #2D2D35;
                border-radius: 12px;
                padding: 1.5rem;
                margin-bottom: 1.5rem;
            }

            .status-ok {
                color: #00E676;
                font-weight: bold;
            }
            .status-error {
                color: #FF1744;
                font-weight: bold;
            }

            div.stButton > button {
                border-radius: 8px;
                font-weight: 600;
            }

            .js-plotly-plot .shapelayer path[style*="rgb(1, 2, 3)"],
            .js-plotly-plot .shapelayer path[style*="rgb(1,2,3)"],
            .js-plotly-plot .shapelayer path[stroke*="rgb(1, 2, 3)"],
            .js-plotly-plot .shapelayer path[stroke*="rgb(1,2,3)"] {
                stroke-opacity: 0.85 !important;
                stroke-width: 1px !important;
                vector-effect: non-scaling-stroke !important;
                shape-rendering: geometricPrecision !important;
            }

            [data-theme="dark"] .js-plotly-plot .shapelayer path[style*="rgb(1, 2, 3)"],
            [data-theme="dark"] .js-plotly-plot .shapelayer path[style*="rgb(1,2,3)"],
            [data-theme="dark"] .js-plotly-plot .shapelayer path[stroke*="rgb(1, 2, 3)"],
            [data-theme="dark"] .js-plotly-plot .shapelayer path[stroke*="rgb(1,2,3)"] {
                stroke: #D1D5DB !important;
                fill: #D1D5DB !important;
            }

            [data-theme="light"] .js-plotly-plot .shapelayer path[style*="rgb(1, 2, 3)"],
            [data-theme="light"] .js-plotly-plot .shapelayer path[style*="rgb(1,2,3)"],
            [data-theme="light"] .js-plotly-plot .shapelayer path[stroke*="rgb(1, 2, 3)"],
            [data-theme="light"] .js-plotly-plot .shapelayer path[stroke*="rgb(1,2,3)"] {
                stroke: #5A626A !important;
                fill: #5A626A !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header() -> None:
    st.markdown("<div class='main-title'>미국옵션 합성 수익곡선 분석기</div>", unsafe_allow_html=True)
    st.markdown("<div class='subtitle'>한국투자증권 OpenAPI 미국옵션 실시간 연동 시뮬레이터</div>", unsafe_allow_html=True)
