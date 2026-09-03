# filegroup_forecast.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional, Tuple, Dict
import numpy as np
import pandas as pd

try:
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.metrics import r2_score, mean_absolute_error
    from sklearn.model_selection import cross_val_score
    SKLEARN_OK = True
except Exception:
    SKLEARN_OK = False

@dataclass
class ForecastConfig:
    horizon_days: int = 60  # Aumentado de 30 para 60 dias
    weekend_threshold_pct: float = 0.95
    capacity_buffer_mb: float = 0.0
    group_filters: Optional[Dict[str, str]] = None
    tz: str = "Europe/Lisbon"
    # NOVO: quando preenchido, a capacidade das LINHAS FUTURAS usa este valor (ex.: soma de MAXSIZE do FG)
    effective_capacity_mb: Optional[float] = None

CANONICAL_COLS = {
    "instanceid": "InstanceID",
    "instance": "Instance",
    "databaseid": "DatabaseID",
    "databasename": "DatabaseName",
    "filegroup_name": "filegroup_name",
    "snapshotdate": "SnapshotDate",
    "total_size_mb": "Total_Size_MB",
    "total_used_mb": "Total_Used_MB",
    # opcional caso você traga isso do upstream
    "capacity_mb": "Capacity_MB",
}

def _normalize_and_map_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c.strip().lower().lstrip("\ufeff") for c in df.columns]
    df.columns = cols
    req = ["instance","databasename","filegroup_name","snapshotdate","total_size_mb","total_used_mb"]
    miss = [k for k in req if k not in cols]
    if miss:
        raise ValueError(f"CSV missing required columns: {miss}")
    return df.rename(columns={k:v for k,v in CANONICAL_COLS.items() if k in cols})

def load_csv(csv_path: str, tz: str = "Europe/Lisbon") -> pd.DataFrame:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV path not found: {csv_path}")
    df = pd.read_csv(csv_path, sep=None, engine="python")
    df = _normalize_and_map_columns(df)
    snap = pd.to_datetime(df["SnapshotDate"], errors="raise")
    if snap.dt.tz is None: snap = snap.dt.tz_localize(tz)
    else: snap = snap.dt.tz_convert(tz)
    df["SnapshotDate"] = snap
    return df.sort_values("SnapshotDate").reset_index(drop=True)

def filter_group(df: pd.DataFrame, filters: Optional[Dict[str, str]]) -> pd.DataFrame:
    if not filters: return df.copy()
    col_map = {c.lower(): c for c in df.columns}
    out = df.copy()
    for k,v in filters.items():
        lk = k.strip().lower()
        if lk not in col_map: raise KeyError(f"Filter column '{k}' not found in data.")
        out = out[out[col_map[lk]] == v]
    if out.empty: raise ValueError(f"No rows match filters: {filters}")
    return out

def consolidate_daily(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df.copy()
    def _agg_one_day(g: pd.DataFrame):
        g = g.sort_values("SnapshotDate")
        last = g.iloc[-1].copy()
        last["Total_Size_MB"] = g["Total_Size_MB"].max()  # captura autogrowth do dia
        if "Capacity_MB" in g.columns:
            last["Capacity_MB"] = g["Capacity_MB"].max()
        return last
    key = df["SnapshotDate"].dt.normalize()
    daily = df.groupby(key, as_index=False).apply(_agg_one_day).reset_index(drop=True)
    return daily.sort_values("SnapshotDate").reset_index(drop=True)

def _fit_time_trend(X: np.ndarray, y: np.ndarray):
    if SKLEARN_OK:
        try: model = Ridge(alpha=1.0, fit_intercept=True, random_state=42)
        except Exception: model = LinearRegression()
        model.fit(X, y)
        class _SkWrap:
            def __init__(self, m): self.m = m; self.sklearn_model = m
            def predict(self, Xnew): return self.m.predict(Xnew)
            @property
            def slope(self): return float(self.m.coef_[0])
        return _SkWrap(model)
    else:
        b,a = np.polyfit(X.ravel().astype(float), y.astype(float), 1)
        class _NpWrap:
            def __init__(self, a_, b_): self._a, self._b = float(a_), float(b_); self.sklearn_model = None
            def predict(self, Xnew): return self._a + self._b * Xnew.ravel()
            @property
            def slope(self): return self._b
        return _NpWrap(a,b)

def train_forecast(df: pd.DataFrame, cfg: ForecastConfig) -> pd.DataFrame:
    if df.empty: raise ValueError("Input dataframe is empty.")
    base = consolidate_daily(df)
    base["t"] = (base["SnapshotDate"] - base["SnapshotDate"].min()).dt.days.astype(float)
    X = base[["t"]].values; y = base["Total_Used_MB"].values.astype(float)
    model = _fit_time_trend(X, y)
    yhat_hist = model.predict(X)

    last_date = base["SnapshotDate"].max()
    fut_dates = pd.date_range(start=last_date + pd.Timedelta(days=1),
                              periods=cfg.horizon_days, freq="D", tz=base["SnapshotDate"].dt.tz)
    #t_future = (fut_dates - base["SnapshotDate"].min()).days.astype(float).reshape(-1,1)
    t_future = (((fut_dates - base["SnapshotDate"].min()) / np.timedelta64(1, "D"))
            .astype(float).to_numpy().reshape(-1, 1))
    yhat_future = model.predict(t_future)

    # Capagem por tendência recente (14d) para evitar explosões por pico isolado
    try:
        recent = base.tail(15).copy()
        deltas = recent["Total_Used_MB"].diff().dropna().values
        robust = max(0.0, min(float(np.median(deltas)) if deltas.size else 0.0,
                              float(np.quantile(deltas,0.75)) if deltas.size else 0.0))
        blended = max(0.0, min(float(getattr(model,"slope",0.0)), robust*1.2))
        last_real = float(base["Total_Used_MB"].iloc[-1])
        days = np.arange(1, len(yhat_future)+1, dtype=float)
        yhat_future = np.minimum(yhat_future, last_real + blended*days)
    except Exception:
        pass

    # Monotonicidade
    last_real = float(base["Total_Used_MB"].iloc[-1])
    yhat_future = np.maximum(yhat_future, last_real)
    yhat_future = np.maximum.accumulate(yhat_future)

    last_capacity_obs = float(base["Total_Size_MB"].iloc[-1])
    hist_out = base[["SnapshotDate","Total_Used_MB","Total_Size_MB"]].copy()
    if "Capacity_MB" in base.columns: hist_out["Capacity_MB"] = base["Capacity_MB"]
    hist_out["yhat"] = yhat_hist; hist_out["is_forecast"] = False

    # NOVO: capacidade futura = efetiva (se informada) ou último tamanho observado
    future_capacity = float(cfg.effective_capacity_mb) if cfg.effective_capacity_mb else last_capacity_obs
    fut_cols = {"SnapshotDate": fut_dates, "Total_Used_MB": np.nan, "yhat": yhat_future,
                "is_forecast": True, "Total_Size_MB": future_capacity}
    if "Capacity_MB" in base.columns: fut_cols["Capacity_MB"] = future_capacity
    fut_out = pd.DataFrame(fut_cols)

    out = pd.concat([hist_out, fut_out], ignore_index=True)
    cap_col = "Capacity_MB" if "Capacity_MB" in out.columns else "Total_Size_MB"
    out["pct_used"] = out["yhat"] / (out[cap_col] + cfg.capacity_buffer_mb)
    out["slope_mb_per_day"] = float(getattr(model,"slope",0.0))

    # --- Model quality metrics (R², MAE, cross-validation) ---
    _sk = getattr(model, "sklearn_model", None)
    if _sk is not None and SKLEARN_OK:
        r2 = _sk.score(X, y)
        y_pred = _sk.predict(X)
        mae = mean_absolute_error(y, y_pred)

        # Cross-validation if enough data
        cv_scores = None
        if len(X) >= 10:
            cv_scores = cross_val_score(_sk, X, y, cv=min(5, len(X) // 2), scoring='r2')

        out.attrs["model_quality"] = {
            "r2_score": round(r2, 4),
            "mae_mb": round(float(mae), 2),
            "cv_r2_mean": round(float(cv_scores.mean()), 4) if cv_scores is not None else None,
            "cv_r2_std": round(float(cv_scores.std()), 4) if cv_scores is not None else None,
            "data_points": len(X),
            "model_type": "Ridge" if hasattr(_sk, 'alpha') else "LinearRegression",
            "confidence": "high" if r2 > 0.8 else "medium" if r2 > 0.5 else "low",
        }
    else:
        # Fallback when sklearn is not available — compute basic R² manually
        ss_res = np.sum((y - model.predict(X)) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        out.attrs["model_quality"] = {
            "r2_score": round(float(r2), 4),
            "mae_mb": round(float(np.mean(np.abs(y - model.predict(X)))), 2),
            "cv_r2_mean": None,
            "cv_r2_std": None,
            "data_points": len(X),
            "model_type": "numpy_polyfit",
            "confidence": "high" if r2 > 0.8 else "medium" if r2 > 0.5 else "low",
        }

    return out

def estimate_capacity_events(forecast_df: pd.DataFrame, cfg: ForecastConfig) -> Dict[str, object]:
    out = {"cross_90_pct_date": None, "hit_100_pct_date": None, "weekend_cross_90": [],
           "slope_mb_per_day": float(forecast_df.loc[~forecast_df["is_forecast"], "slope_mb_per_day"].tail(1).values[0])
           if "slope_mb_per_day" in forecast_df.columns else None}

    # Include model quality metrics from train_forecast
    model_quality = forecast_df.attrs.get("model_quality")
    if model_quality:
        out["model_quality"] = model_quality
        r2 = model_quality.get("r2_score", 0)
        if r2 < 0.3:
            out["warnings"] = out.get("warnings", [])
            out["warnings"].append(
                f"Low model quality (R\u00b2={r2:.2f}). Predictions may be unreliable. "
                "Consider using more historical data or a different model."
            )
    
    # Verificar se o threshold já foi cruzado nos dados históricos
    hist = forecast_df[~forecast_df["is_forecast"]].copy()
    fut = forecast_df[forecast_df["is_forecast"]].copy()
    
    if fut.empty: return out
    thr = cfg.weekend_threshold_pct
    
    # Se já cruzou o threshold no passado, não considerar cruzamento futuro como novo evento
    already_crossed = hist["pct_used"] >= thr
    if already_crossed.any():
        # Se já cruzou no passado, só detectar se vai atingir 100%
        full = fut[fut["pct_used"] >= 1.0]
        if not full.empty: 
            out["hit_100_pct_date"] = full["SnapshotDate"].iloc[0]
        
        # Contar fins de semana em alerta no futuro
        fut["dow"] = fut["SnapshotDate"].dt.dayofweek
        wk = fut[(fut["dow"].isin([5,6])) & (fut["pct_used"] >= thr)]
        for _,row in wk.iterrows():
            out["weekend_cross_90"].append((row["SnapshotDate"], float(row["pct_used"])))
    else:
        # Se não cruzou no passado, detectar primeiro cruzamento no futuro
        cross = fut[fut["pct_used"] >= thr]
        if not cross.empty: 
            out["cross_90_pct_date"] = cross["SnapshotDate"].iloc[0]
        
        full = fut[fut["pct_used"] >= 1.0]
        if not full.empty: 
            out["hit_100_pct_date"] = full["SnapshotDate"].iloc[0]
        
        fut["dow"] = fut["SnapshotDate"].dt.dayofweek
        wk = fut[(fut["dow"].isin([5,6])) & (fut["pct_used"] >= thr)]
        for _,row in wk.iterrows():
            out["weekend_cross_90"].append((row["SnapshotDate"], float(row["pct_used"])))
    
    return out

def plot_forecast(forecast_df: pd.DataFrame, title: str, output_png: Optional[str] = None) -> str:
    import matplotlib.pyplot as plt
    hist = forecast_df[~forecast_df["is_forecast"]]
    cap_col = "Capacity_MB" if "Capacity_MB" in forecast_df.columns else "Total_Size_MB"
    plt.figure(figsize=(10,5))
    plt.plot(hist["SnapshotDate"], hist["Total_Used_MB"], label="Usado (real)")
    plt.plot(forecast_df["SnapshotDate"], forecast_df["yhat"], linestyle="--", label="Previsão (yhat)")
    plt.plot(forecast_df["SnapshotDate"], forecast_df[cap_col], linestyle=":", label="Capacidade")
    plt.xlabel("Data"); plt.ylabel("MB"); plt.title(title); plt.legend(); plt.tight_layout()
    output_png = output_png or "forecast.png"; plt.savefig(output_png, dpi=150); plt.close()
    return output_png

def run_pipeline(csv_path: str, cfg: ForecastConfig, output_dir: str = ".", save_prefix: str = "filegroup"
                ) -> Tuple[str, str, Dict[str, object]]:
    os.makedirs(output_dir, exist_ok=True)
    df = load_csv(csv_path, tz=cfg.tz)
    filtered = filter_group(df, cfg.group_filters)
    daily = consolidate_daily(filtered)
    fcst = train_forecast(daily, cfg)
    events = estimate_capacity_events(fcst, cfg)
    title_bits = []
    for k in ["Instance","DatabaseName","filegroup_name"]:
        if cfg.group_filters and k in cfg.group_filters:
            title_bits.append(f"{k}={cfg.group_filters[k]}")
    title = " | ".join(title_bits) if title_bits else "Filegroup Forecast"
    csv_out = os.path.join(output_dir, f"{save_prefix}_forecast.csv")
    png_out = os.path.join(output_dir, f"{save_prefix}_forecast.png")
    fcst.to_csv(csv_out, index=False)
    plot_forecast(fcst, title=title, output_png=png_out)
    return csv_out, png_out, events

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python filegroup_forecast.py <csv_path> [filters 'k=v;k2=v2'] [horizon_days] [effective_capacity_mb or 'auto']")
        raise SystemExit(1)
    csv_path = sys.argv[1]
    filters_arg = sys.argv[2] if len(sys.argv) >= 3 else None
    horizon = int(sys.argv[3]) if len(sys.argv) >= 4 else 21
    effcap_arg = sys.argv[4] if len(sys.argv) >= 5 else None
    filters = {}
    if filters_arg:
        for pair in filters_arg.split(";"):
            if "=" in pair:
                k,v = pair.split("=",1); filters[k]=v
    effcap = None
    if effcap_arg and effcap_arg.lower() != "auto":
        try: effcap = float(effcap_arg)
        except: effcap = None
    cfg = ForecastConfig(horizon_days=horizon, group_filters=filters if filters else None,
                         effective_capacity_mb=effcap)
    csv_out, png_out, events = run_pipeline(csv_path, cfg, output_dir=".", save_prefix="cli_run")
    print("Forecast CSV:", csv_out)
    print("Forecast PNG:", png_out)
    print("Eventos:", events)
