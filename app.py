import streamlit as st
import pandas as pd

# ===================== Page basic settings =====================
st.set_page_config(
    page_title="Clinic Discount Distribution Platform",
    layout="wide"
)

DATA_PATH = "Doctor list_with_Dashboard.xlsx"

# 侧边栏上传：可以上传单一或多保险公司 Excel
uploaded_file = st.sidebar.file_uploader(
    "Upload insurer data (single or multi-sheet Excel)",
    type=["xlsx"]
)

# ===================== Data loading =====================
@st.cache_data
def load_data(file) -> pd.DataFrame:
    """
    file 可以是：
    - 本地路径字符串（默认 Doctor list_with_Dashboard.xlsx）
    - 上传的文件对象（单保险公司或多保险公司）
    总是按 sheet_name=None 读取：每个 sheet 名视为 insurer。
    自动兼容 dicount/discount、discount band 等列名差异。
    """
    sheets_dict = pd.read_excel(file, sheet_name=None)

    all_dfs = []

    for sheet_name, df in sheets_dict.items():
        if df is None or df.empty:
            continue

        # 统一列名
        df.columns = [c.strip().lower() for c in df.columns]
        lower_cols = df.columns

        def find_first_contains(*keywords):
            for c in lower_cols:
                if all(k in c for k in keywords):
                    return c
            return None

        col_map = {}

        # chi_location
        chi_loc_col = find_first_contains("chilocation") or find_first_contains("chi", "location")
        if chi_loc_col:
            col_map[chi_loc_col] = "chi_location"

        # service_type
        svc_col = find_first_contains("servicetype") or find_first_contains("service", "type")
        if svc_col:
            col_map[svc_col] = "service_type"

        # 折扣系数 dicount / discount
        disc_col = None
        for name in ["dicount", "discount"]:
            if name in lower_cols:
                disc_col = name
                break
        if disc_col is None:
            disc_col = find_first_contains("disc")
        if disc_col:
            col_map[disc_col] = "dicount"

        # 折扣档位 discount band / discountband
        band_col = find_first_contains("discount", "band")
        if band_col:
            col_map[band_col] = "discount_band"

        # 应用重命名
        df = df.rename(columns=col_map)

        # 如果没有折扣列，跳过该 sheet
        if "dicount" not in df.columns:
            continue

        # 为缺失列补空
        for c in ["chi_location", "service_type", "discount_band"]:
            if c not in df.columns:
                df[c] = None

        # 只保留核心列
        keep_cols = ["chi_location", "service_type", "dicount", "discount_band"]
        df = df[keep_cols].copy()

        # 清洗折扣列
        df["dicount"] = pd.to_numeric(df["dicount"], errors="coerce")
        df = df[df["dicount"].notna()]

        # insurer = sheet 名（单 sheet 文件也是用 sheet 名当公司名）
        df["insurer"] = sheet_name

        all_dfs.append(df)

    if not all_dfs:
        return pd.DataFrame()

    return pd.concat(all_dfs, ignore_index=True)


# 先看有没有上传文件，有的话优先用上传的；否则用本地默认总表
try:
    if uploaded_file is not None:
        df = load_data(uploaded_file)
    else:
        df = load_data(DATA_PATH)
except Exception as e:
    st.error(f"加载 Excel 数据出错：{e}")
    st.stop()

if df.empty:
    st.error("Excel 中未识别到有效的折扣数据，请检查各工作表的列名。")
    st.stop()

# ===================== Sidebar filters =====================
st.sidebar.header("Filters")

# 保险公司列表
insurer_options = sorted(df["insurer"].dropna().unique())
selected_insurer = st.sidebar.selectbox(
    "Insurance company (sheet)",
    options=insurer_options,
)

df_ins = df[df["insurer"] == selected_insurer].copy()

# Chi Location 多选
chi_loc_options = sorted(df_ins["chi_location"].dropna().unique())
selected_chi_locs = st.sidebar.multiselect(
    "Chi Location",
    options=chi_loc_options,
    default=chi_loc_options,
)

# Service type 多选
service_options = sorted(df_ins["service_type"].dropna().unique())
selected_services = st.sidebar.multiselect(
    "Service type",
    options=service_options,
    default=service_options,
)

# 应用筛选
filtered = df_ins.copy()
if selected_chi_locs:
    filtered = filtered[filtered["chi_location"].isin(selected_chi_locs)]
if selected_services:
    filtered = filtered[filtered["service_type"].isin(selected_services)]

if filtered.empty:
    st.warning("No records under current filters. Please try different options.")
    st.stop()

# ===================== KPIs =====================
st.title("Clinic Discount Distribution Platform")
st.caption(f"Current insurer (sheet): **{selected_insurer}**")

col1, col2 = st.columns(2)

# KPI1：整体平均折扣
with col1:
    avg_discount = filtered["dicount"].mean()
    st.metric("Average discount", f"{avg_discount * 100:.2f}%")

# KPI2：最高 discount band 的平均折扣
with col2:
    if "discount_band" in filtered.columns and filtered["discount_band"].notna().any():
        # 找出最高的一个 band（例如 '90%-99%'）
        top_band = sorted(filtered["discount_band"].dropna().unique())[-1]
        top_band_df = filtered[filtered["discount_band"] == top_band]
        top_band_avg = top_band_df["dicount"].mean()
        st.metric(
            f"Average discount ({top_band})",
            f"{top_band_avg * 100:.2f}%"
        )
    else:
        st.metric("Average discount (top band)", "N/A")

# ===================== Chart: discount band distribution =====================
st.subheader("Discount band distribution (number of clinics)")

if "discount_band" in filtered.columns and filtered["discount_band"].notna().any():
    chart_data = (
        filtered["discount_band"]
        .value_counts()
        .sort_index()
        .rename_axis("Discount band")
        .reset_index(name="Clinic count")
    )

    # 1）柱状图还是用原始按 band 的数据
    st.bar_chart(
        data=chart_data.set_index("Discount band"),
        use_container_width=True,
    )

    # 2）在表格下方加总计行
    total_count = chart_data["Clinic count"].sum()
    total_row = pd.DataFrame(
        {"Discount band": ["Total"], "Clinic count": [total_count]}
    )
    chart_with_total = pd.concat([chart_data, total_row], ignore_index=True)

    # 表格下方显示 Total 的数据
    st.dataframe(chart_with_total)
else:
    st.info("當前保險公司數據中未檢測到折扣檔位（discount band）列。")


