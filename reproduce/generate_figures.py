"""公開レポートの集計図を描画する。

このスクリプトは元データを読まない。読めるようにもしていない。
価格（HistData.com）と市場予想（個人ブログ・みんかぶFX）は再配布の許諾が
確認できないため公開物に含めておらず、手元で再計算はできない。

したがってここに置いてあるのは、元調査で算出済みの集計値だけである。
個別イベントの日付、価格系列、市場予想値は含めない。

数値の出どころ:

- 1分値幅、平均R、t値、評価件数、サプライズ絶対値の階級別度数
  … 非公開の元データに対する集計結果。値は元レポートと一致させてある
- 信頼区間
  … 上の平均R・t値・件数から、このスクリプト内で導出している（下の ci_from_t）。
    ブートストラップではなく、t分布に基づく区間である

「再現」と名乗っていないのは、このスクリプト単体では再現にならないためである。
元データからの再計算手順は limits.html に記載している。
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets"


def ci_from_t(mean, t_stat, n, level: float = 0.95):
    """平均値・t値・件数から両側95%信頼区間を導く。

    t = mean / SE なので SE = mean / t。区間は mean ± t_crit(df=n-1) * SE。
    ブートストラップではない。標本平均の分布に t 分布を仮定した区間である。
    """
    from scipy import stats

    mean = np.asarray(mean, dtype=float)
    se = np.abs(mean / np.asarray(t_stat, dtype=float))
    crit = stats.t.ppf(0.5 + level / 2, np.asarray(n, dtype=float) - 1)
    return np.vstack((mean - crit * se, mean + crit * se))


def configure_font() -> str:
    """Windows上で利用可能な日本語フォントを選び、文字化けを防ぐ。"""
    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Yu Gothic", "Meiryo", "MS Gothic", "Noto Sans CJK JP"):
        if candidate in available:
            plt.rcParams["font.family"] = candidate
            plt.rcParams["axes.unicode_minus"] = False
            return candidate
    raise RuntimeError("日本語フォントが見つかりません。Yu Gothic または Meiryo を導入してください。")


def save(fig: plt.Figure, name: str) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT / name, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def minute_ranges() -> None:
    minutes = np.array([0, 1, 5, 10])
    usdjpy = np.array([34.0, 12.1, 9.2, 6.7])
    xauusd = np.array([9.85, 4.18, 2.93, 2.64])
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 4.6))
    panels = (
        (axes[0], usdjpy, "ドル円", "1分値幅（pips）", (2.0, 4.0), "#1e6f9f"),
        (axes[1], xauusd, "ゴールド", "1分値幅（ドル）", (1.0, 1.2), "#d98a19"),
    )
    for ax, values, title, ylabel, pre_band, color in panels:
        ax.axhspan(pre_band[0], pre_band[1], color="#dbe6eb", alpha=0.9, label="発表10〜1分前の中央値帯")
        ax.plot(minutes, values, marker="o", linewidth=2.6, color=color, label="発表分以降")
        for x, y in zip(minutes, values, strict=True):
            ax.annotate(f"{y:g}", (x, y), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=9)
        ax.set_title(title, fontweight="bold")
        ax.set_xlabel("発表からの経過（分）")
        ax.set_ylabel(ylabel)
        ax.set_xticks(minutes, ["発表分", "+1", "+5", "+10"])
        ax.grid(axis="y", alpha=0.24)
        ax.legend(frameon=False, fontsize=8, loc="upper right")
    fig.suptitle("値動きの大部分は発表直後に集中", fontsize=16, fontweight="bold")
    fig.text(0.5, -0.01, "集計: 2020〜2026年、コロナ期を除外。線は個別価格ではなく各時点の中央値。", ha="center", fontsize=9, color="#526172")
    fig.tight_layout()
    save(fig, "minute-ranges.png")


def surprise_distribution() -> None:
    labels = ["0–24", "25–49", "50–99", "100–199", "200以上"]
    # 階級別度数。いずれも元データからの集計値。
    # 2013–2019 は雇用統計83回すべて。2020–2026 はコロナ期を除外した64回
    # （元レポートの分析対象と同じ母集団。中央値はそれぞれ 35千人 / 64.5千人）。
    unused_counts = np.array([27, 25, 20, 11, 0], dtype=float)
    tuning_counts = np.array([14, 10, 20, 8, 12], dtype=float)
    unused_pct = unused_counts / unused_counts.sum() * 100
    tuning_pct = tuning_counts / tuning_counts.sum() * 100
    x = np.arange(len(labels))
    width = 0.36
    fig, ax = plt.subplots(figsize=(10.8, 5.1))
    ax.bar(x - width / 2, unused_pct, width, label="2013–2019（未使用）", color="#1e6f9f")
    ax.bar(x + width / 2, tuning_pct, width, label="2020–2026（調整）", color="#d98a19")
    ax.set_title("サプライズ絶対値の分布は期間で異なった", fontsize=16, fontweight="bold")
    ax.set_xlabel("サプライズ絶対値の階級（千人）")
    ax.set_ylabel("各期間に占める割合（%）")
    ax.set_xticks(x, labels)
    ax.grid(axis="y", alpha=0.24)
    ax.legend(frameon=False)
    ax.text(0.02, 0.95, "中央値: 35千人 → 64千人", transform=ax.transAxes, ha="left", va="top", fontsize=11, fontweight="bold", color="#16324f")
    fig.text(0.5, -0.01, "階級別の集計値のみを表示。個別イベントの予想値・実績値は掲載していない。", ha="center", fontsize=9, color="#526172")
    fig.tight_layout()
    save(fig, "surprise-distribution.png")


def oos_comparison() -> None:
    instruments = ["ゴールド", "ドル円"]
    # 平均R・t値・評価件数は元データに対する集計結果（元レポートと一致）。
    # 信頼区間はそこから導出する。端点を書き写すのではなく計算するのは、
    # 導出過程を読み手が検算できるようにするため。
    tuning = np.array([1.135, 0.537])
    unused = np.array([0.139, 0.290])
    tuning_t, tuning_n = np.array([3.55, 2.35]), np.array([51, 55])
    unused_t, unused_n = np.array([0.63, 1.74]), np.array([70, 64])
    tuning_ci = ci_from_t(tuning, tuning_t, tuning_n)
    unused_ci = ci_from_t(unused, unused_t, unused_n)
    x = np.arange(len(instruments))
    width = 0.34
    fig, ax = plt.subplots(figsize=(9.7, 5.5))
    ax.axhline(0, color="#354a5d", linewidth=1.1)
    ax.bar(x - width / 2, tuning, width, yerr=np.vstack((tuning - tuning_ci[0], tuning_ci[1] - tuning)), capsize=6, label="2020–2026（調整）", color="#d98a19")
    ax.bar(x + width / 2, unused, width, yerr=np.vstack((unused - unused_ci[0], unused_ci[1] - unused)), capsize=6, label="2013–2019（未使用）", color="#1e6f9f")
    for xpos, value in zip(x - width / 2, tuning, strict=True):
        ax.text(xpos, value + 0.05, f"{value:+.3f}R", ha="center", fontsize=9, fontweight="bold", bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 1.5})
    for xpos, value in zip(x + width / 2, unused, strict=True):
        ax.text(xpos, value + 0.05, f"{value:+.3f}R", ha="center", fontsize=9, fontweight="bold", bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 1.5})
    ax.set_title("調整期間で最も良く見えた対象が最も大きく劣化", fontsize=15, fontweight="bold")
    ax.set_ylabel("1観測あたりの平均（R）")
    ax.set_xticks(x, instruments)
    ax.set_ylim(-0.45, 2.05)
    ax.grid(axis="y", alpha=0.24)
    ax.legend(frameon=False)
    ax.text(0.18, 0.76, "88%減", transform=ax.transAxes, color="#96362f", fontsize=17, fontweight="bold")
    ax.text(0.69, 0.49, "46%減", transform=ax.transAxes, color="#96362f", fontsize=14, fontweight="bold")
    fig.text(0.5, -0.01, "エラーバーは平均値とt値から求めた95%信頼区間（t分布）。未使用期間はいずれも0をまたいだ。", ha="center", fontsize=9, color="#526172")
    fig.tight_layout()
    save(fig, "oos-comparison.png")


def main() -> None:
    font = configure_font()
    minute_ranges()
    surprise_distribution()
    oos_comparison()
    print(f"generated 3 figures in {OUTPUT} (font={font})")


if __name__ == "__main__":
    main()
