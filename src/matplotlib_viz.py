import io
import base64

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def get_filtered_data(history, args):
    data = history[:]
    try:
        limit_n = int(args.get("limit_n", 30))
    except (TypeError, ValueError):
        limit_n = 30
    if limit_n < 1:
        limit_n = 1
    return data[-limit_n:]


def build_plot_url(data, temp_unit="C"):
    if not data:
        return None

    x = [row["timestamp"] for row in data]
    if temp_unit == "F":
        y = [(row["temperature"] * 9.0 / 5.0) + 32.0 for row in data]
    else:
        y = [row["temperature"] for row in data]

    plt.figure(figsize=(12, 4))
    plt.plot(x, y, marker="o", linestyle="-", color="tab:blue", linewidth=2)
    plt.title("Temperature History")
    plt.ylabel(f"Temperature [{temp_unit}]")
    plt.xticks(rotation=45)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    return base64.b64encode(buf.getvalue()).decode("utf-8")
