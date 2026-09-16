import re
from itertools import combinations

import pandas as pd
import plotly.express as px
import streamlit as st

CSV_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/danggok_meals_184.csv"

st.set_page_config(page_title="급식 규칙 찾기", layout="wide")


# ---------------------------------------------------------------------------
# 데이터 불러오기 & 전처리
# ---------------------------------------------------------------------------
@st.cache_data
def load_data():
    df = pd.read_csv(CSV_URL, encoding="utf-8")
    return df


def clean_menu_name(name: str) -> str:
    """괄호(반각/전각)와 그 안의 내용을 모두 제거하고 공백을 정리한다."""
    name = re.sub(r"\([^()]*\)", "", name)
    name = re.sub(r"（[^（）]*）", "", name)
    return name.strip()


@st.cache_data
def build_baskets(df: pd.DataFrame):
    """하루 식단 한 줄 = 장바구니 한 건. 메뉴 이름을 정리해서 리스트로 만든다."""
    baskets = []
    for _, row in df.iterrows():
        raw_items = str(row["메뉴"]).split("|")
        cleaned = [clean_menu_name(item) for item in raw_items]
        cleaned = [c for c in cleaned if c]  # 빈 문자열 제거
        # 같은 날 중복 메뉴 제거(순서 유지)
        seen = []
        for c in cleaned:
            if c not in seen:
                seen.append(c)
        if seen:
            baskets.append({"날짜": row["날짜"], "식사": row.get("식사", ""), "메뉴목록": seen})
    return baskets


@st.cache_data
def build_rules(baskets):
    n = len(baskets)

    # 메뉴별 등장 횟수(지지도 분모)
    item_count = {}
    # 메뉴 쌍별 동시 등장 횟수
    pair_count = {}

    for b in baskets:
        items = sorted(set(b["메뉴목록"]))
        for it in items:
            item_count[it] = item_count.get(it, 0) + 1
        for a, c in combinations(items, 2):
            key = (a, c)
            pair_count[key] = pair_count.get(key, 0) + 1

    pair_rows = []  # 쌍 단위(방향 없음) - 그래프용
    rule_rows = []  # 규칙 단위(방향 있음) - 표용

    for (a, c), co in pair_count.items():
        support_pair = co / n
        conf_ac = co / item_count[a]
        conf_ca = co / item_count[c]
        lift = (co * n) / (item_count[a] * item_count[c])

        pair_rows.append(
            {"메뉴1": a, "메뉴2": c, "동시": co, "지지도": support_pair, "향상도": lift}
        )

        rule_rows.append(
            {
                "조건": a,
                "결과": c,
                "동시": co,
                "지지도": support_pair,
                "신뢰도": conf_ac,
                "향상도": lift,
            }
        )
        rule_rows.append(
            {
                "조건": c,
                "결과": a,
                "동시": co,
                "지지도": support_pair,
                "신뢰도": conf_ca,
                "향상도": lift,
            }
        )

    rules_df = pd.DataFrame(rule_rows)
    pairs_df = pd.DataFrame(pair_rows)
    return rules_df, pairs_df, item_count


# ---------------------------------------------------------------------------
# 화면 구성
# ---------------------------------------------------------------------------
st.title("🍱 급식 규칙 찾기")
st.caption("같은 날 함께 나온 메뉴들 사이의 연관 규칙(지지도·신뢰도·향상도)을 살펴봅니다.")

with st.spinner("데이터를 불러오는 중..."):
    df = load_data()
    baskets = build_baskets(df)
    rules_df, pairs_df, item_count = build_rules(baskets)

n_days = len(baskets)
n_menus = len(item_count)
n_pairs = len(pairs_df)

st.markdown(f"**급식 일수: {n_days}일 · 메뉴 종류 수: {n_menus}개 · 함께 나온 적이 있는 메뉴 쌍의 수: {n_pairs}쌍**")

st.divider()

col1, col2 = st.columns([1, 1])

with col1:
    sort_option = st.selectbox(
        "정렬 기준",
        ["향상도 순", "신뢰도 순", "동시 순"],
        index=0,
    )

with col2:
    all_menus = sorted(item_count.keys())
    selected_menu = st.selectbox(
        "메뉴로 좁혀보기 (해당 메뉴가 들어간 규칙만 보기)",
        ["전체 보기"] + all_menus,
        index=0,
    )

sort_col_map = {"향상도 순": "향상도", "신뢰도 순": "신뢰도", "동시 순": "동시"}
sort_col = sort_col_map[sort_option]

# 표 필터 & 정렬
display_rules = rules_df.copy()
if selected_menu != "전체 보기":
    display_rules = display_rules[
        (display_rules["조건"] == selected_menu) | (display_rules["결과"] == selected_menu)
    ]

display_rules = display_rules.sort_values(sort_col, ascending=False).reset_index(drop=True)

st.subheader("연관 규칙 표")
st.dataframe(
    display_rules.style.format(
        {"지지도": "{:.3f}", "신뢰도": "{:.3f}", "향상도": "{:.2f}"}
    ),
    width='stretch',
    height=420,
)

st.divider()

# 그래프: 향상도 상위 10개 (쌍 단위, 방향 중복 없이)
st.subheader("향상도 상위 10개 메뉴 쌍")

chart_pairs = pairs_df.copy()
if selected_menu != "전체 보기":
    chart_pairs = chart_pairs[
        (chart_pairs["메뉴1"] == selected_menu) | (chart_pairs["메뉴2"] == selected_menu)
    ]

top10 = chart_pairs.sort_values("향상도", ascending=False).head(10).copy()

if top10.empty:
    st.info("선택한 메뉴에 대한 연관 쌍이 없습니다.")
else:
    top10["쌍"] = top10["메뉴1"] + " ↔ " + top10["메뉴2"]
    top10 = top10.sort_values("향상도", ascending=True)  # 가로 막대그래프에서 위로 갈수록 크게

    fig = px.bar(
        top10,
        x="향상도",
        y="쌍",
        orientation="h",
        text="향상도",
        hover_data={"동시": True, "지지도": ":.3f", "향상도": ":.2f"},
        title="향상도 상위 10개 메뉴 쌍" + (f" (필터: {selected_menu})" if selected_menu != "전체 보기" else ""),
    )
    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
    fig.update_layout(yaxis_title="", xaxis_title="향상도(Lift)", height=500)
    st.plotly_chart(fig, width='stretch')
