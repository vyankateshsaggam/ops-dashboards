"""
export.py
----------
Helper functions to export filtered data / charts in multiple formats.
"""
import io
import pandas as pd
import streamlit as st


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Data")
        workbook = writer.book
        worksheet = writer.sheets["Data"]
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#7C3AED", "font_color": "white"})
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
        worksheet.autofit()
    return buf.getvalue()


def render_export_buttons(df: pd.DataFrame, key_prefix: str, chart_fig=None):
    """Renders CSV / Excel (/ PNG if a plotly fig is supplied) download buttons."""
    cols = st.columns(3 if chart_fig is not None else 2)
    with cols[0]:
        st.download_button("⬇️ CSV", to_csv_bytes(df), file_name=f"{key_prefix}.csv",
                            mime="text/csv", use_container_width=True, key=f"{key_prefix}_csv")
    with cols[1]:
        st.download_button("⬇️ Excel", to_excel_bytes(df), file_name=f"{key_prefix}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True, key=f"{key_prefix}_xlsx")
    if chart_fig is not None:
        with cols[2]:
            try:
                png_bytes = chart_fig.to_image(format="png", scale=2)
                st.download_button("⬇️ PNG", png_bytes, file_name=f"{key_prefix}.png",
                                    mime="image/png", use_container_width=True, key=f"{key_prefix}_png")
            except Exception:
                st.caption("PNG export needs `kaleido` installed.")
