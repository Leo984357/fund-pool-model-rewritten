import pandas as pd

def _bytes_to_int(x):
    if isinstance(x, (bytes, bytearray)):
        return int.from_bytes(x, byteorder="little", signed=False)
    try:
        return int(x)
    except Exception:
        return pd.NA

def normalize_topn_for_gui(df: pd.DataFrame) -> pd.DataFrame:
    """把 rank 转 int，并做基本格式化（fund_code、date），仅做显示层处理。"""
    out = df.copy()

    if "rank" in out.columns:
        out["rank"] = out["rank"].map(_bytes_to_int).astype("Int64")

    if "fund_code" in out.columns:
        out["fund_code"] = (
            out["fund_code"].astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .str.zfill(6)
        )

    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date.astype(str)

    return out