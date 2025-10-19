import tkinter as tk
from tkinter import ttk
import threading
import time
import math
from collections import deque
import statistics
import serial
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from tkinter import messagebox, filedialog
import os

# ---------------- CONFIG ---------------- #
PUERTO = "COM7"
BAUDIOS = 9600
J = 0.000055776625  # Momento de inercia (kg·m²)
D = 0.055           # Diámetro del rodillo (m)
SAMPLE_INTERVAL = 0.05  # s, muestreo durante el test
TEST_DURATION = 15       # s por test
REG_WINDOW_S = 0.35      # ventana para regresión (s)
MIN_SAMPLES_REG = 4      # mínimo de puntos en la ventana para estimar alpha
NUM_TESTS = 5            # número de tests
# ---------------------------------------- #

# Datos en tiempo real
rpm_actual = 0.0
rpm_suave = 0.0
velocidad = 0.0
torque = 0.0
potencia_hp = 0.0

omega_anterior = 0.0
t_anterior = time.time()

# Test state
test_iniciado = False
tiempo_restante = 0
rpm_test = []  # lista de (timestamp, rpm_actual) durante el test
test_results = [None] * NUM_TESTS
test_samples = [None] * NUM_TESTS   # <-- guardar muestras por test para las gráficas
current_test_idx = 0
test_start_time = None

# Datos para plot durante el test
times_plot = deque()
rpms_plot = deque(maxlen=500)

# Locks
data_lock = threading.Lock()

# Mostrar máximos / tabla
mostrar_maximos = False

# ---------------- UI (dark minimal, VSCode-like) ---------------- #
root = tk.Tk()
root.title("Dyno Stand - RC")
root.geometry("1000x760")
root.configure(bg="#1e1e1e")

# color scheme
BG = "#1e1e1e"
PANEL = "#252526"
CARD = "#2a2d2f"
FG = "#d4d4d4"
ACCENT = "#0db99b"
MUTED = "#9aa0a6"
root.configure(bg=BG)

style = ttk.Style(root)
style.theme_use("default")
style.configure("TButton", font=("Segoe UI", 11), padding=6)
style.configure("TLabel", background=BG, foreground=FG)
style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"), foreground=ACCENT, background=BG)
style.configure("Outline.TButton",
                foreground=FG,
                background=CARD,
                relief="flat",
                borderwidth=1)
style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))

# ---------------- UI LAYOUT (redesign like image) ---------------- #
# Header
header = tk.Frame(root, bg=BG, padx=14, pady=10)
header.pack(fill="x")
titulo = tk.Label(header, text=f"Dyno Stand RC — Tests ({NUM_TESTS})", fg=ACCENT, bg=BG, font=("Segoe UI", 18, "bold"))
titulo.pack(side="left")
sub = tk.Label(header, text="Panel de pruebas", fg=MUTED, bg=BG, font=("Segoe UI", 10))
sub.pack(side="left", padx=(10,0), pady=(6,0))

# Main frames
main_frame = tk.Frame(root, bg=BG)
main_frame.pack(fill="both", expand=True, padx=10, pady=8)

left_frame = tk.Frame(main_frame, bg=BG)
left_frame.pack(side="left", fill="both", expand=True, padx=(0,8))

right_frame = tk.Frame(main_frame, bg=BG, width=380)
right_frame.pack(side="right", fill="y")

# Top readout (left)
readout_frame = tk.Frame(left_frame, bg=CARD, bd=0)
readout_frame.pack(fill="x", pady=(0,8))

rpm_label = tk.Label(readout_frame, text=f"RPM: {rpm_actual:.0f}", fg=ACCENT, bg=CARD, font=("Segoe UI", 20, "bold"))
rpm_label.pack(side="left", padx=12, pady=10)

datos_label = tk.Label(readout_frame, text="", fg=FG, bg=CARD, font=("Segoe UI", 11), justify="left")
datos_label.pack(side="left", padx=18)

# status
status_frame = tk.Frame(left_frame, bg=BG)
status_frame.pack(fill="x", pady=(0,8))

canvas_ind = tk.Canvas(status_frame, width=40, height=40, bg=BG, highlightthickness=0)
canvas_ind.pack(side="left", padx=(4,8))
circulo = canvas_ind.create_oval(6, 6, 34, 34, fill="#3a3a3a", outline="#3a3a3a")

cuenta_label = tk.Label(status_frame, text="", fg=MUTED, bg=BG, font=("Segoe UI", 12))
cuenta_label.pack(side="left", padx=6)

# LEFT: gauge + plots area
left_top = tk.Frame(left_frame, bg=BG)
left_top.pack(fill="x", expand=False)

left_bottom = tk.Frame(left_frame, bg=BG)
left_bottom.pack(fill="both", expand=True, pady=(8,0))

# Gauge card
gauge_card = tk.Frame(left_top, bg=CARD, bd=0)
gauge_card.pack(side="left", padx=(0,10), pady=6)

gauge_canvas = tk.Canvas(gauge_card, width=240, height=240, bg=CARD, highlightthickness=0)
gauge_canvas.pack(padx=12, pady=12)

ind_row = tk.Frame(gauge_card, bg=CARD)
ind_row.pack(fill="x", padx=12, pady=(0,10))
led_green = tk.Canvas(ind_row, width=14, height=14, bg=CARD, highlightthickness=0)
led_green.create_oval(2,2,12,12, fill="#0b6e4f", outline="#0b6e4f")
led_green.pack(side="left", padx=(0,8))
led_red = tk.Canvas(ind_row, width=14, height=14, bg=CARD, highlightthickness=0)
led_red.create_oval(2,2,12,12, fill="#6e0b0b", outline="#6e0b0b")
led_red.pack(side="left", padx=(0,8))
led_lbl = tk.Label(ind_row, text="1/1(s)", fg=MUTED, bg=CARD, font=("Segoe UI", 9))
led_lbl.pack(side="left", padx=(6,0))

# Plot card (two stacked subplots)
plot_card = tk.Frame(left_top, bg=CARD)
plot_card.pack(side="left", fill="both", expand=True, pady=6)

fig, (ax_line, ax_bar) = plt.subplots(2, 1, figsize=(9.5, 6), sharex=True, gridspec_kw={"height_ratios":[1,0.7]})
fig.patch.set_facecolor(BG)
ax_line.set_facecolor(PANEL)
ax_bar.set_facecolor(PANEL)
for a in (ax_line, ax_bar):
    a.tick_params(colors=FG)
    a.xaxis.label.set_color(FG)
    a.yaxis.label.set_color(FG)
    for s in a.spines.values():
        s.set_color(MUTED)

linea_line, = ax_line.plot([], [], color=ACCENT, linewidth=2)
ax_line.set_xlim(0, TEST_DURATION)
ax_line.set_ylim(0, 15000)
ax_line.set_ylabel("RPM")

# bottom plot: show speed in km/h (convert from RPM when drawing)
ax_bar.set_xlim(0, TEST_DURATION)
ax_bar.set_ylim(0, 150)                # default in km/h
ax_bar.set_ylabel("km/h")
ax_bar.yaxis.label.set_color(FG)
ax_bar.set_xlabel("tiempo(s)")

canvas = FigureCanvasTkAgg(fig, master=plot_card)
canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

# LEFT bottom: metrics card
metrics_card = tk.Frame(left_bottom, bg=CARD)
metrics_card.pack(side="left", fill="both", padx=(0,12), pady=6, ipadx=6, ipady=6)

metrics_title = tk.Label(metrics_card, text="Resumen (último test)", fg=FG, bg=CARD, font=("Segoe UI", 11, "bold"))
metrics_title.pack(anchor="w", padx=10, pady=(6,4))

metrics_table = tk.Frame(metrics_card, bg=CARD)
metrics_table.pack(padx=8, pady=(0,8))

labels_info = [("km/h", "--"), ("km/h-max", "--"), ("HP", "--"), ("Torque N·m", "--"), ("a(0-100)", "--")]
metric_widgets = {}
for k, v in labels_info:
    r = tk.Frame(metrics_table, bg=CARD)
    r.pack(anchor="w", fill="x")
    # make the "km/h" label use the bright FG color, others muted
    label_fg = FG if k == "km/h" else MUTED
    tk.Label(r, text=f"{k}", fg=label_fg, bg=CARD, width=12, anchor="w", font=("Segoe UI", 9)).pack(side="left", padx=(6,8), pady=4)
    val = tk.Label(r, text=v, fg=FG, bg=CARD, font=("Segoe UI", 9, "bold"))
    val.pack(side="left")
    metric_widgets[k] = val

left_extra = tk.Frame(left_bottom, bg=BG)
left_extra.pack(side="left", fill="both", expand=True, pady=6)

# RIGHT: results table + controls
tabla_panel = tk.Frame(right_frame, bg=BG)
tabla_panel.pack(fill="both", expand=False, pady=6, padx=6)

tabla_title = tk.Label(tabla_panel, text="Resultados Tests", fg=FG, bg=BG, font=("Segoe UI", 13, "bold"))
tabla_title.pack(anchor="w", padx=6, pady=(6,4))

hdr_frame = tk.Frame(tabla_panel, bg=BG)
hdr_frame.pack(fill="x", padx=6)
headers = ["Test", "RPM máx", "Vel (km/h)", "Torque (N·m)", "Potencia (HP)"]
widths = [8,10,12,16,14]
for j, h in enumerate(headers):
    lbl = tk.Label(hdr_frame, text=h, fg=FG, bg=BG, font=("Segoe UI", 10, "bold"), width=widths[j], anchor="w")
    lbl.grid(row=0, column=j, padx=2)

rows_frame = tk.Frame(tabla_panel, bg=BG)
rows_frame.pack(fill="both", padx=6, pady=(4,6))

test_labels = []
for i in range(NUM_TESTS):
    row = tk.Frame(rows_frame, bg=CARD)
    row.pack(fill="x", pady=4)
    lbl0 = tk.Label(row, text=f"Test {i+1}", fg=ACCENT, bg=CARD, font=("Segoe UI", 11, "bold"), width=8, anchor="w")
    lbl0.pack(side="left", padx=6, pady=6)
    lbl1 = tk.Label(row, text="—", fg=FG, bg=CARD, font=("Segoe UI", 11), width=10, anchor="w")
    lbl1.pack(side="left", padx=6)
    lbl2 = tk.Label(row, text="—", fg=FG, bg=CARD, font=("Segoe UI", 11), width=12, anchor="w")
    lbl2.pack(side="left", padx=6)
    lbl3 = tk.Label(row, text="—", fg=FG, bg=CARD, font=("Segoe UI", 11), width=16, anchor="w")
    lbl3.pack(side="left", padx=6)
    lbl4 = tk.Label(row, text="—", fg=FG, bg=CARD, font=("Segoe UI", 11), width=14, anchor="w")
    lbl4.pack(side="left", padx=6)
    test_labels.append((lbl0, lbl1, lbl2, lbl3, lbl4))

# Mean row
mean_row = tk.Frame(rows_frame, bg="#1f2426")
mean_row.pack(fill="x", pady=(8,0))
mean_lbl0 = tk.Label(mean_row, text="Media", fg=FG, bg="#1f2426", font=("Segoe UI", 11, "bold"), width=8, anchor="w")
mean_lbl0.pack(side="left", padx=6, pady=6)
mean_lbl1 = tk.Label(mean_row, text="—", fg=FG, bg="#1f2426", font=("Segoe UI", 11), width=10, anchor="w")
mean_lbl1.pack(side="left", padx=6)
mean_lbl2 = tk.Label(mean_row, text="—", fg=FG, bg="#1f2426", font=("Segoe UI", 11), width=12, anchor="w")
mean_lbl2.pack(side="left", padx=6)
mean_lbl3 = tk.Label(mean_row, text="—", fg=FG, bg="#1f2426", font=("Segoe UI", 11), width=16, anchor="w")
mean_lbl3.pack(side="left", padx=6)
mean_lbl4 = tk.Label(mean_row, text="—", fg=FG, bg="#1f2426", font=("Segoe UI", 11), width=14, anchor="w")
mean_lbl4.pack(side="left", padx=6)

# ---------------- AUX ---------------- #
def update_tests_table():
    for i in range(NUM_TESTS):
        res = test_results[i]
        lbls = test_labels[i]
        lbls[0].config(text=f"Test {i+1}")
        if res is None:
            lbls[1].config(text="—")
            lbls[2].config(text="—")
            lbls[3].config(text="—")
            lbls[4].config(text="—")
        else:
            lbls[1].config(text=f"{res['rpm_max']:.0f}")
            lbls[2].config(text=f"{res['velocidad_max']:.2f}")
            lbls[3].config(text=f"{res['torque_max']:.6f}")
            lbls[4].config(text=f"{res['potencia_max']:.4f}")

    if all(r is not None for r in test_results):
        rpm_list = [r['rpm_max'] for r in test_results]
        vel_list = [r['velocidad_max'] for r in test_results]
        tq_list = [r['torque_max'] for r in test_results]
        p_list = [r['potencia_max'] for r in test_results]
        mean_rpm = statistics.mean(rpm_list) if rpm_list else 0.0
        mean_vel = statistics.mean(vel_list) if vel_list else 0.0
        mean_tq = statistics.mean(tq_list) if tq_list else 0.0
        mean_p = statistics.mean(p_list) if p_list else 0.0
        mean_lbl1.config(text=f"{mean_rpm:.0f}")
        mean_lbl2.config(text=f"{mean_vel:.2f}")
        mean_lbl3.config(text=f"{mean_tq:.6f}")
        mean_lbl4.config(text=f"{mean_p:.4f}")
    else:
        mean_lbl1.config(text="—")
        mean_lbl2.config(text="—")
        mean_lbl3.config(text="—")
        mean_lbl4.config(text="—")

def median_filter(values, window=3):
    if len(values) < 1:
        return []
    if window <= 1:
        return values[:]
    out = []
    half = window // 2
    n = len(values)
    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        out.append(statistics.median(values[start:end]))
    return out

def slope_least_squares(ts, ys):
    n = len(ts)
    if n < 2:
        return 0.0
    sum_t = sum(ts)
    sum_y = sum(ys)
    sum_tt = sum(t*t for t in ts)
    sum_ty = sum(t*y for t, y in zip(ts, ys))
    denom = n * sum_tt - sum_t * sum_t
    if abs(denom) < 1e-12:
        return 0.0
    return (n * sum_ty - sum_t * sum_y) / denom

def generar_pdf():
    """Genera PDF con la tabla de resultados y por cada test dos gráficas (RPM y km/h)."""
    if not all(r is not None for r in test_results):
        messagebox.showwarning("Aviso", "Los tests no están completados.")
        return

    filename = filedialog.asksaveasfilename(defaultextension=".pdf",
                                            filetypes=[("PDF files","*.pdf")],
                                            initialfile="dyno_results.pdf")
    if not filename:
        return

    try:
        with PdfPages(filename) as pdf:
            # Página 1: tabla resumen
            fig, ax = plt.subplots(figsize=(8.27, 11.69))  # A4
            ax.axis('off')
            headers = ["Test", "RPM máx", "Vel (km/h)", "Torque (N·m)", "Potencia (HP)"]
            rows = []
            for i, res in enumerate(test_results):
                if res is None:
                    rows.append([f"Test {i+1}", "—", "—", "—", "—"])
                else:
                    rows.append([f"Test {i+1}",
                                 f"{res['rpm_max']:.0f}",
                                 f"{res['velocidad_max']:.2f}",
                                 f"{res['torque_max']:.6f}",
                                 f"{res['potencia_max']:.4f}"])
            table = ax.table(cellText=rows, colLabels=headers, loc='center', cellLoc='center')
            table.auto_set_font_size(False)
            table.set_fontsize(10)
            table.scale(1, 1.5)
            ax.set_title("Resultados de Tests", fontsize=14)
            pdf.savefig(fig, bbox_inches='tight')
            plt.close(fig)

            # Págs por test: RPM y km/h
            for i in range(NUM_TESTS):
                samples = test_samples[i]
                fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.27, 11.69/1.5))
                fig.suptitle(f"Test {i+1}", fontsize=12)
                if samples:
                    t0 = samples[0][0]
                    ts = [t - t0 for t, r in samples]
                    rpms = [r for t, r in samples]
                    a1.plot(ts, rpms, color=ACCENT)
                    a1.set_ylabel("RPM")
                    v_kmh = [(r * math.pi * D * 60) / 1000 for r in rpms]
                    a2.plot(ts, v_kmh, color="#e07b39")
                    a2.set_ylabel("km/h")
                    a2.set_xlabel("Tiempo (s)")
                    a1.grid(True, alpha=0.2)
                    a2.grid(True, alpha=0.2)
                else:
                    a1.text(0.5, 0.5, "Sin datos", ha='center', va='center')
                    a2.text(0.5, 0.5, "Sin datos", ha='center', va='center')
                pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)
        messagebox.showinfo("PDF creado", f"PDF guardado en:\n{filename}")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo crear el PDF:\n{e}")

# Controls card
controls_container = tk.Frame(tabla_panel, bg=BG)
controls_container.pack(fill="x", pady=8, padx=6)

control_card = tk.Frame(controls_container, bg=CARD)
control_card.pack(fill="x", padx=6, pady=6)

btn_col = tk.Frame(control_card, bg=CARD)
btn_col.pack(side="left", padx=(6,12), pady=10)

primary_btn = tk.Button(btn_col,
                        text=f"Iniciar Test 1",
                        command=lambda: iniciar_test(),
                        bg=ACCENT,
                        fg=BG,
                        activebackground="#0a8f72",
                        activeforeground=BG,
                        bd=0,
                        relief="flat",
                        font=("Segoe UI", 11, "bold"),
                        padx=14, pady=8)
primary_btn.pack(side="left", padx=(0,10))

secondary_btn = ttk.Button(btn_col, text="Reiniciar todo", style="Outline.TButton", command=lambda: reset_all())
secondary_btn.pack(side="left")

# New: Descargar PDF button (disabled hasta completar los tests)
desc_btn = tk.Button(btn_col,
                     text="Descargar PDF",
                     command=lambda: generar_pdf(),
                     bg=CARD,
                     fg=FG,
                     bd=0,
                     relief="flat",
                     font=("Segoe UI", 10),
                     padx=8, pady=6,
                     state="disabled")
desc_btn.pack(side="left", padx=(8,0))

info_col = tk.Frame(control_card, bg=CARD)
info_col.pack(side="left", fill="x", expand=True, padx=(12,6), pady=8)

info_title = tk.Label(info_col, text="Procedimiento", fg=FG, bg=CARD, font=("Segoe UI", 10, "bold"))
info_title.pack(anchor="w")
info_text = tk.Label(info_col,
                     text=f"Haz {NUM_TESTS} tests consecutivos. La gráfica se actualiza solo durante cada test.",
                     fg=MUTED,
                     bg=CARD,
                     font=("Segoe UI", 10),
                     justify="left",
                     wraplength=240)
info_text.pack(anchor="w", pady=(4,0))

# compatibility
test_btn = primary_btn
reset_btn = secondary_btn

# ---------------- helper: gauge drawing ---------------- #
def draw_gauge(rpm_val):
    gauge_canvas.delete("gauge")
    w = 240; h = 240
    cx, cy = w//2, h//2
    radius = 90
    gauge_canvas.create_oval(cx-radius, cy-radius, cx+radius, cy+radius, fill=CARD, outline="", tags="gauge")
    gauge_canvas.create_arc(cx-radius, cy-radius, cx+radius, cy+radius,
                            start=150, extent=240, style="arc", width=12, outline="#2f3234", tags="gauge")
    perc = min(max(rpm_val / 15000.0, 0.0), 1.0)
    gauge_canvas.create_arc(cx-radius, cy-radius, cx+radius, cy+radius,
                            start=150, extent=240*perc, style="arc", width=12, outline=ACCENT, tags="gauge")
    ang = math.radians(150 - 240*perc)
    nx = cx + int((radius-18) * math.cos(ang))
    ny = cy - int((radius-18) * math.sin(ang))
    gauge_canvas.create_line(cx, cy, nx, ny, fill="#ffffff", width=3, tags="gauge")
    gauge_canvas.create_oval(cx-8, cy-8, cx+8, cy+8, fill="#ffffff", tags="gauge")
    gauge_canvas.create_text(cx, cy+28, text=f"{rpm_val:.0f} RPM", fill=FG, font=("Segoe UI", 10, "bold"), tags="gauge")

draw_gauge(0.0)

# ---------------- SERIAL ---------------- #
def leer_datos():
    global rpm_actual
    try:
        with serial.Serial(PUERTO, BAUDIOS, timeout=1) as arduino:
            print(f"Conectado a {PUERTO}")
            while True:
                linea = arduino.readline().decode(errors='ignore').strip()
                if linea.startswith("RPM:"):
                    try:
                        val = float(linea.split(":")[1].strip())
                        with data_lock:
                            rpm_actual = val
                    except:
                        pass
    except serial.SerialException:
        print(f"No se pudo abrir {PUERTO}")

# ---------------- ACTUALIZAR ---------------- #
def actualizar():
    global rpm_suave, velocidad, torque, potencia_hp, omega_anterior, t_anterior

    with data_lock:
        r_actual = rpm_actual

    rpm_suave = (rpm_suave * 0.3) + (r_actual * 0.7)

    omega = (2 * math.pi * rpm_suave) / 60
    tiempo_actual = time.time()

    delta_t = tiempo_actual - t_anterior
    if delta_t > 0:
        alpha = (omega - omega_anterior) / delta_t
        torque = J * alpha
    else:
        torque = 0.0

    omega_anterior = omega
    t_anterior = tiempo_actual

    potencia_hp = (torque * omega) / 745.7
    velocidad = (rpm_suave * math.pi * D * 60) / 1000

    rpm_label.config(text=f"RPM: {rpm_suave:,.0f}")
    draw_gauge(rpm_suave)

    if test_iniciado:
        datos_label.config(text=f"Velocidad: {velocidad:,.2f} km/h\nTest actual: {current_test_idx+1}/{NUM_TESTS}")
    elif mostrar_maximos:
        datos_label.config(
            text=f"Vel (último test): {velocidad:.2f} km/h\n"
                 f"Torque (último): {torque:.6f} N·m\n"
                 f"Potencia (último): {potencia_hp:.4f} HP"
        )
    else:
        datos_label.config(
            text=f"Velocidad: {velocidad:,.2f} km/h\n"
                 f"Torque: {torque:.6f} N·m\n"
                 f"Potencia: {potencia_hp:.4f} HP"
        )

    # actualizar plots
    if test_iniciado and test_start_time is not None and times_plot:
        max_r = max(rpms_plot) if rpms_plot else 15000
        ax_line.set_ylim(0, max(2000, max_r * 1.1))
        xs = [min(max(0.0, x), TEST_DURATION) for x in times_plot]
        linea_line.set_data(xs, list(rpms_plot))
        ax_line.set_xlim(0, TEST_DURATION)

        # bottom: convert RPM -> km/h for display
        ax_bar.clear()
        ax_bar.set_facecolor(PANEL)
        ax_bar.tick_params(colors=FG)
        for s in ax_bar.spines.values():
            s.set_color(MUTED)
        ax_bar.set_xlim(0, TEST_DURATION)
        # convert max rpm to km/h for y limits
        max_v_kmh = (max_r * math.pi * D * 60) / 1000 if max_r else 150.0
        ax_bar.set_ylim(0, max(20, max_v_kmh * 1.1))
        ax_bar.set_ylabel("km/h")
        ax_bar.yaxis.label.set_color(FG)
        if times_plot and rpms_plot:
            vals_kmh = [ (r * math.pi * D * 60) / 1000 for r in rpms_plot ]
            ax_bar.bar(xs, vals_kmh, width=0.08, color=ACCENT, alpha=0.9)
        canvas.draw()
    else:
        ax_line.set_xlim(0, TEST_DURATION)
        if not rpms_plot:
            ax_line.set_ylim(0, 15000)
            linea_line.set_data([], [])
            ax_bar.clear()
            ax_bar.set_facecolor(PANEL)
            ax_bar.set_xlim(0, TEST_DURATION)
            ax_bar.set_ylim(0, 150)    # default km/h when empty
            ax_bar.set_ylabel("km/h")
            ax_bar.yaxis.label.set_color(FG)
        else:
            max_r = max(rpms_plot)
            ax_line.set_ylim(0, max(2000, max_r * 1.1))
            linea_line.set_data(list(times_plot), list(rpms_plot))
            ax_bar.clear()
            ax_bar.set_facecolor(PANEL)
            ax_bar.set_xlim(0, TEST_DURATION)
            # convert to km/h for limits and bars
            max_v_kmh = (max_r * math.pi * D * 60) / 1000
            ax_bar.set_ylim(0, max(20, max_v_kmh * 1.1))
            ax_bar.set_ylabel("km/h")
            ax_bar.yaxis.label.set_color(FG)
            if times_plot and rpms_plot:
                vals_kmh = [ (r * math.pi * D * 60) / 1000 for r in rpms_plot ]
                ax_bar.bar(list(times_plot), vals_kmh, width=0.08, color=ACCENT, alpha=0.9)
        canvas.draw()

    root.after(100, actualizar)

# ---------------- TEST (muestreo y cálculo) ---------------- #
def iniciar_test():
    global test_iniciado, rpm_test, tiempo_restante, mostrar_maximos, current_test_idx, times_plot, rpms_plot
    if test_iniciado:
        return
    if current_test_idx >= NUM_TESTS:
        return
    test_iniciado = True
    rpm_test = []
    tiempo_restante = TEST_DURATION
    mostrar_maximos = False
    canvas_ind.itemconfig(circulo, fill="#0b6e4f")
    times_plot.clear()
    rpms_plot.clear()
    linea_line.set_data([], [])
    ax_line.set_xlim(0, TEST_DURATION)
    ax_line.set_ylim(0, 15000)
    ax_bar.clear()
    ax_bar.set_xlim(0, TEST_DURATION)
    ax_bar.set_ylim(0, 150)   # reset bottom plot to km/h range
    ax_bar.set_ylabel("km/h")
    ax_bar.yaxis.label.set_color(FG)
    canvas.draw()
    cuenta_atras_inicial(3)

def cuenta_atras_inicial(segundos):
    global test_start_time
    if segundos > 0:
        cuenta_label.config(text=f"Comienza en: {segundos}")
        root.after(1000, lambda: cuenta_atras_inicial(segundos-1))
    else:
        test_start_time = time.time()
        with data_lock:
            r0 = rpm_actual if rpm_actual is not None else 0.0
        times_plot.append(0.0)
        rpms_plot.append(r0)
        rpm_test.append((test_start_time, r0))
        cuenta_label.config(text="¡Acelera!")
        root.after(0, sample_test)
        root.after(0, cuenta_test)

def cuenta_test():
    global tiempo_restante
    if tiempo_restante > 0:
        cuenta_label.config(text=f"Tiempo restante: {tiempo_restante}s")
        tiempo_restante -= 1
        root.after(1000, cuenta_test)
    else:
        finalizar_test()

def sample_test():
    global rpm_test, times_plot, rpms_plot
    if not test_iniciado or test_start_time is None:
        return
    t = time.time()
    with data_lock:
        r = rpm_actual
    if r is not None and r > 0.5:
        rpm_test.append((t, r))
        rel_t = t - test_start_time
        if rel_t < 0:
            rel_t = 0.0
        if rel_t > TEST_DURATION:
            rel_t = TEST_DURATION
        if rel_t <= TEST_DURATION:
            times_plot.append(rel_t)
            rpms_plot.append(r)
    root.after(int(SAMPLE_INTERVAL * 1000), sample_test)

def finalizar_test():
    global test_iniciado, rpm_test, test_results, mostrar_maximos, current_test_idx, test_start_time, test_samples
    # guardar muestras del test actual (aunque esté vacío)
    try:
        test_samples[current_test_idx] = rpm_test.copy()
    except Exception:
        test_samples[current_test_idx] = rpm_test[:]

    test_iniciado = False
    canvas_ind.itemconfig(circulo, fill="#3a3a3a")

    rpm_max_test = 0.0
    velocidad_max_test = 0.0
    torque_max_test = 0.0
    potencia_max_test = 0.0

    if not rpm_test:
        test_results[current_test_idx] = {
            "rpm_max": rpm_max_test,
            "velocidad_max": velocidad_max_test,
            "torque_max": torque_max_test,
            "potencia_max": potencia_max_test,
        }
        update_tests_table()
        current_test_idx += 1
        mostrar_maximos = True
        cuenta_label.config(text="")
        test_start_time = None
        # limpiar resumen si no hay datos
        metric_widgets["km/h"].config(text="--")
        metric_widgets["km/h-max"].config(text="--")
        metric_widgets["HP"].config(text="--")
        metric_widgets["Torque N·m"].config(text="--")
        metric_widgets["a(0-100)"].config(text="--")
        if current_test_idx < NUM_TESTS:
            test_btn.config(text=f"Iniciar Test {current_test_idx+1}")
        else:
            test_btn.config(text="Tests completados", state="disabled")
        return

    tiempos_lst = [t for t, r in rpm_test]
    rpms_vals = [r for t, r in rpm_test]

    rpm_max_test = max(rpms_vals) if rpms_vals else 0.0
    velocidad_max_test = (rpm_max_test * math.pi * D * 60) / 1000 if rpm_max_test else 0.0

    # Filtrado mediano ligero
    rpms_filtered = median_filter(rpms_vals, window=3)
    omegas = [(2 * math.pi * r) / 60 for r in rpms_filtered]

    torques = []
    potencias = []

    n = len(omegas)
    for i in range(n):
        ti = tiempos_lst[i]
        j0 = i
        while j0 > 0 and (ti - tiempos_lst[j0 - 1]) <= REG_WINDOW_S:
            j0 -= 1
        rec_ts = [t - tiempos_lst[j0] for t in tiempos_lst[j0:i+1]]
        window_omegas = omegas[j0:i+1]
        if len(rec_ts) >= MIN_SAMPLES_REG:
            alpha = slope_least_squares(rec_ts, window_omegas)
            total_dt = tiempos_lst[i] - tiempos_lst[j0]
            if total_dt > 0 and total_dt <= REG_WINDOW_S:
                torque_inst = J * alpha
                potencia_inst = (torque_inst * window_omegas[-1]) / 745.7
                torques.append(torque_inst)
                potencias.append(potencia_inst)

    torque_max_test = max((abs(t) for t in torques), default=0.0)
    potencia_max_test = max((abs(p) for p in potencias), default=0.0)

    test_results[current_test_idx] = {
        "rpm_max": rpm_max_test,
        "velocidad_max": velocidad_max_test,
        "torque_max": torque_max_test,
        "potencia_max": potencia_max_test,
    }
    update_tests_table()

    current_test_idx += 1
    mostrar_maximos = True
    cuenta_label.config(text="")
    test_start_time = None

    # si ya se completaron todos los tests, habilitar botón PDF
    if current_test_idx >= NUM_TESTS:
        test_btn.config(text="Tests completados", state="disabled")
        try:
            desc_btn.config(state="normal")
        except Exception:
            pass
    else:
        test_btn.config(text=f"Iniciar Test {current_test_idx+1}")

# ---------------- RESET ---------------- #
def reset_all():
    global test_results, current_test_idx, mostrar_maximos, times_plot, rpms_plot, test_start_time, test_samples
    test_results = [None] * NUM_TESTS
    test_samples = [None] * NUM_TESTS
    current_test_idx = 0
    mostrar_maximos = False
    times_plot.clear()
    rpms_plot.clear()
    test_start_time = None
    test_btn.config(text=f"Iniciar Test 1", state="normal")
    try:
        desc_btn.config(state="disabled")
    except Exception:
        pass
    update_tests_table()
    cuenta_label.config(text="")
    linea_line.set_data([], [])
    ax_line.set_xlim(0, TEST_DURATION)
    ax_line.set_ylim(0, 15000)
    ax_bar.clear()
    ax_bar.set_xlim(0, TEST_DURATION)
    ax_bar.set_ylim(0, 150)   # reset bottom plot to km/h range
    ax_bar.set_ylabel("km/h")
    ax_bar.yaxis.label.set_color(FG)
    canvas.draw()
    # limpiar resumen
    try:
        metric_widgets["km/h"].config(text="--")
        metric_widgets["km/h-max"].config(text="--")
        metric_widgets["HP"].config(text="--")
        metric_widgets["Torque N·m"].config(text="--")
        metric_widgets["a(0-100)"].config(text="--")
    except Exception:
        pass

# ---------------- RUN ---------------- #
threading.Thread(target=leer_datos, daemon=True).start()
root.after(100, actualizar)
root.mainloop()