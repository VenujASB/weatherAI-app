import tkinter as tk
from tkinter import ttk, messagebox
import threading, requests, time, datetime, json, os, math
from io import BytesIO
from PIL import Image, ImageTk
import ttkbootstrap as tb

# Matplotlib embed for trend chart
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

API_KEY = "1c1be22d2a124d622abb3cc8778e5616"  # <-- put your key here
BASE_URL = "https://api.openweathermap.org/data/2.5"

HISTORY_MAX = 5
FAV_FILE = "favorites.json"

# --------- Persistence helpers ---------
def load_favorites():
    try:
        if os.path.exists(FAV_FILE):
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except:
        pass
    return []

def save_favorites(favs):
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(favs, f, ensure_ascii=False, indent=2)
    except:
        pass

def center_window(window, width, height):
    window.update_idletasks()
    x = (window.winfo_screenwidth() // 2) - (width // 2)
    y = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


# --------- Simple weather background animations (Canvas) ---------
class WeatherAnimation:
    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self.running = False
        self.items = []
        self.mode = None  # "sun", "rain", "snow"

    def clear(self):
        for item in self.items:
            self.canvas.delete(item)
        self.items.clear()

    def stop(self):
        self.running = False
        self.clear()

    def start(self, mode):
        self.stop()
        self.mode = mode
        self.running = True
        w = self.canvas.winfo_width() or 480
        h = self.canvas.winfo_height() or 320

        if mode == "sun":
            # sun center + rays
            cx, cy, r = w - 80, 80, 30
            sun = self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#FFD54F", outline="")
            self.items.append(sun)
            rays = []
            for i in range(12):
                angle = i * math.pi / 6
                x1 = cx + math.cos(angle) * (r + 5)
                y1 = cy + math.sin(angle) * (r + 5)
                x2 = cx + math.cos(angle) * (r + 25)
                y2 = cy + math.sin(angle) * (r + 25)
                ray = self.canvas.create_line(x1, y1, x2, y2, width=3)
                rays.append(ray); self.items.append(ray)

            def pulse(ph=0):
                if not self.running or self.mode != "sun": return
                scale = 1 + 0.03 * math.sin(ph)
                sr = int(r * scale)
                self.canvas.coords(sun, cx - sr, cy - sr, cx + sr, cy + sr)
                for i, ray in enumerate(rays):
                    angle = i * math.pi / 6
                    length = r + 25 + 5 * math.sin(ph + i*0.4)
                    x1 = cx + math.cos(angle) * (r + 5)
                    y1 = cy + math.sin(angle) * (r + 5)
                    x2 = cx + math.cos(angle) * length
                    y2 = cy + math.sin(angle) * length
                    self.canvas.coords(ray, x1, y1, x2, y2)
                self.canvas.after(40, lambda: pulse(ph + 0.2))
            pulse()

        elif mode == "rain":
            # falling lines
            import random
            drops = []
            for _ in range(70):
                x = random.randint(0, w)
                y = random.randint(-h, 0)
                l = random.randint(8, 16)
                d = self.canvas.create_line(x, y, x, y + l)
                drops.append((d, l)); self.items.append(d)

            def fall():
                if not self.running or self.mode != "rain": return
                for d, l in drops:
                    x1, y1, x2, y2 = self.canvas.coords(d)
                    y1 += 8; y2 += 8
                    if y1 > self.canvas.winfo_height():
                        ny = -10
                        self.canvas.coords(d, x1, ny, x1, ny + l)
                    else:
                        self.canvas.coords(d, x1, y1, x2, y2)
                self.canvas.after(30, fall)
            fall()

        elif mode == "snow":
            # gentle falling circles
            import random
            flakes = []
            for _ in range(40):
                x = random.randint(0, w); y = random.randint(-h, 0)
                r = random.randint(2, 4)
                f = self.canvas.create_oval(x-r, y-r, x+r, y+r, fill="#FFFFFF", outline="")
                flakes.append((f, r, random.uniform(0.5, 1.5), random.uniform(0, 6.28)))
                self.items.append(f)

            def drift():
                if not self.running or self.mode != "snow": return
                for i, (f, r, spd, phase) in enumerate(flakes):
                    x1, y1, x2, y2 = self.canvas.coords(f)
                    cx = (x1 + x2) / 2; cy = (y1 + y2) / 2
                    cy += spd
                    cx += math.sin(phase) * 0.8
                    phase += 0.1
                    if cy - r > self.canvas.winfo_height():
                        cy = -r
                    self.canvas.coords(f, cx - r, cy - r, cx + r, cy + r)
                    flakes[i] = (f, r, spd, phase)
                self.canvas.after(40, drift)
            drift()

# --------- Main App ---------
class WeatherApp:
    def __init__(self, root: tb.Window):
        self.root = root
        # Set default size and center window
        center_window(self.root, 800, 600)   # Default window size
        self.root.minsize(600, 500)          # Minimum size so it doesn’t shrink too much

        self.search_history = []
        self.favorites = load_favorites()
        self.current_theme = None
        self.bg_color = None

        # Auto theme by local time
        hour = datetime.datetime.now().hour
        self.set_theme("flatly" if 7 <= hour < 19 else "superhero")

        self.root.title("🌦 AI Weather Dashboard")
        self.root.geometry("820x600")

        # Navbar
        self.navbar = tk.Frame(root, bg=self.bg_color)
        self.navbar.pack(fill="x")
        tb.Button(self.navbar, text="🏠 Home", bootstyle="secondary-outline",
                  command=lambda: self.show_page(self.home_frame)).pack(side="left", padx=6, pady=4)
        tb.Button(self.navbar, text="📅 History", bootstyle="info-outline",
                  command=self.load_history).pack(side="left", padx=6, pady=4)
        tb.Button(self.navbar, text="⭐ Favorites", bootstyle="warning-outline",
                  command=self.load_favorites_page).pack(side="left", padx=6, pady=4)
        tb.Button(self.navbar, text="🌗 Theme", bootstyle="warning-outline",
                  command=self.toggle_theme).pack(side="right", padx=6, pady=4)

        # Live clock
        self.clock_label = tk.Label(self.navbar, text="", font=("Arial", 11), fg="white", bg=self.bg_color)
        self.clock_label.pack(side="right", padx=10)
        self.update_clock()

        # Pages
        self.home_frame = tk.Frame(root, bg=self.bg_color)
        self.loading_frame = tk.Frame(root, bg=self.bg_color)
        self.today_frame = tk.Frame(root, bg=self.bg_color)
        self.forecast_frame = tk.Frame(root, bg=self.bg_color)
        self.history_frame = tk.Frame(root, bg=self.bg_color)
        self.favorites_frame = tk.Frame(root, bg=self.bg_color)

        self.build_home()
        self.build_loading()
        self.build_today()
        self.build_forecast()
        self.build_history()
        self.build_favorites()

        self.show_page(self.home_frame)

    # ---- Theme / Clock ----
    def set_theme(self, theme_name):
        self.current_theme = theme_name
        self.style = tb.Style(theme=theme_name)
        self.style.theme_use(theme_name)
        self.bg_color = "#121212" if theme_name in ("superhero", "cyborg", "darkly") else "#ffffff"

    def toggle_theme(self):
        self.set_theme("flatly" if self.current_theme == "superhero" else "superhero")
        # Repaint backgrounds
        for f in (self.navbar, self.home_frame, self.loading_frame, self.today_frame,
                  self.forecast_frame, self.history_frame, self.favorites_frame):
            f.configure(bg=self.bg_color)
        self.clock_label.configure(bg=self.bg_color)
        self.show_page(self.home_frame)

    def update_clock(self):
        self.clock_label.config(text=time.strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000, self.update_clock)

    # ---- UI Builders ----
    def build_home(self):
        f = self.home_frame
        for w in f.winfo_children(): w.destroy()
        tk.Label(f, text="🌍 Enter City & Country (optional)", font=("Arial", 18, "bold"),
                 fg="white", bg=self.bg_color).pack(pady=20)

        form = tk.Frame(f, bg=self.bg_color)
        form.pack(pady=10)

        self.city_entry = ttk.Entry(form, font=("Arial", 12), width=20)
        self.city_entry.grid(row=0, column=0, padx=5)
        self.city_entry.insert(0, "London")

        self.country_entry = ttk.Entry(form, font=("Arial", 12), width=8)
        self.country_entry.grid(row=0, column=1, padx=5)
        self.country_entry.insert(0, "UK")

        self.unit_var = tk.StringVar(value="Celsius")
        unit_menu = ttk.Combobox(form, textvariable=self.unit_var, values=["Celsius", "Fahrenheit"],
                                 width=12, state="readonly")
        unit_menu.grid(row=0, column=2, padx=5)

        tb.Button(f, text="📍 Use My Location", bootstyle="info-outline",
                  command=self.use_my_location).pack(pady=8)
        tb.Button(f, text="Get Weather 🚀", bootstyle="success", command=self.start_weather).pack(pady=18)

    def build_loading(self):
        f = self.loading_frame
        for w in f.winfo_children(): w.destroy()
        tk.Label(f, text="Fetching data...", font=("Arial", 16), fg="white", bg=self.bg_color).pack(pady=240)

    def build_today(self):
        f = self.today_frame
        for w in f.winfo_children(): w.destroy()

        # Animation canvas behind content
        self.anim_canvas = tk.Canvas(f, bg=self.bg_color, highlightthickness=0)
        self.anim_canvas.pack(fill="both", expand=True)
        self.anim = WeatherAnimation(self.anim_canvas)

        # Overlay content frame
        self.today_overlay = tk.Frame(self.anim_canvas, bg="#1E1E1E", padx=16, pady=16)
        self.today_overlay.place(relx=0.5, rely=0.52, anchor="center")  # centered

        self.today_icon_label = tk.Label(self.today_overlay, bg="#1E1E1E")
        self.today_icon_label.pack(pady=6)
        self.today_text_label = tk.Label(self.today_overlay, text="", font=("Arial", 14),
                                         fg="white", bg="#1E1E1E", justify="center")
        self.today_text_label.pack(pady=6)

        buttons = tk.Frame(self.today_overlay, bg="#1E1E1E")
        buttons.pack(pady=8)
        tb.Button(buttons, text="5-Day Forecast 📅", bootstyle="warning", command=self.load_forecast).pack(side="left", padx=6)
        tb.Button(buttons, text="⭐ Save City", bootstyle="info", command=self.save_current_favorite).pack(side="left", padx=6)
        tb.Button(buttons, text="⬅ Back", bootstyle="secondary", command=lambda: self.show_page(self.home_frame)).pack(side="left", padx=6)

    def build_forecast(self):
        f = self.forecast_frame
        for w in f.winfo_children(): w.destroy()
        self.forecast_top = tk.Frame(f, bg=self.bg_color)
        self.forecast_top.pack(fill="x", pady=8)
        tb.Button(self.forecast_top, text="⬅ Back", bootstyle="secondary",
                  command=lambda: self.show_page(self.today_frame)).pack(side="left", padx=8)

        self.cards_row = tk.Frame(f, bg=self.bg_color)
        self.cards_row.pack(pady=10)

        # Matplotlib trend figure
        self.fig = Figure(figsize=(6.5, 2.8), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Temperature Trend (next 5 days)")
        self.ax.set_xlabel("Date")
        self.ax.set_ylabel("Temp")
        self.canvas_mpl = FigureCanvasTkAgg(self.fig, master=f)
        self.canvas_mpl.get_tk_widget().pack(pady=10)

    def build_history(self):
        f = self.history_frame
        for w in f.winfo_children(): w.destroy()
        tk.Label(f, text="Recent Searches", font=("Arial", 16, "bold"),
                 fg="white", bg=self.bg_color).pack(pady=16)
        self.history_list = tk.Frame(f, bg=self.bg_color)
        self.history_list.pack()
        tb.Button(f, text="⬅ Back", bootstyle="secondary",
                  command=lambda: self.show_page(self.home_frame)).pack(pady=10)

    def build_favorites(self):
        f = self.favorites_frame
        for w in f.winfo_children(): w.destroy()
        tk.Label(f, text="⭐ Favorites", font=("Arial", 16, "bold"),
                 fg="white", bg=self.bg_color).pack(pady=16)
        self.fav_list = tk.Frame(f, bg=self.bg_color)
        self.fav_list.pack()
        tb.Button(f, text="⬅ Back", bootstyle="secondary",
                  command=lambda: self.show_page(self.home_frame)).pack(pady=10)

    # ---- Page switching with fade ----
    def show_page(self, frame):
        for f in (self.home_frame, self.loading_frame, self.today_frame,
                  self.forecast_frame, self.history_frame, self.favorites_frame):
            f.pack_forget()
        frame.pack(fill="both", expand=True)
        threading.Thread(target=lambda: self._animate_fade(frame)).start()

    def _animate_fade(self, frame):
        try:
            for alpha in range(7, 11):
                self.root.attributes("-alpha", alpha / 10)
                time.sleep(0.02)
            self.root.attributes("-alpha", 1.0)
        except:
            pass

    # ---- Actions ----
    def use_my_location(self):
        def work():
            try:
                data = requests.get("https://ipinfo.io/json", timeout=6).json()
                city = data.get("city", "")
                country = data.get("country", "")
                self.root.after(0, lambda: self._fill_location(city, country))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Location Error", str(e), parent=self.root))
        threading.Thread(target=work, daemon=True).start()

    def _fill_location(self, city, country):
        if city:
            self.city_entry.delete(0, "end"); self.city_entry.insert(0, city)
        if country:
            self.country_entry.delete(0, "end"); self.country_entry.insert(0, country)

    def start_weather(self):
        city = self.city_entry.get().strip()
        country = self.country_entry.get().strip()
        unit = "metric" if self.unit_var.get() == "Celsius" else "imperial"
        if not city:
            messagebox.showerror("Missing Input", "Please enter a city name.", parent=self.root)
            return
        self.show_page(self.loading_frame)

        def work():
            weather = self._get_weather(city, country, unit)
            self.root.after(0, lambda: self._update_today(weather, unit))
        threading.Thread(target=work, daemon=True).start()

    def _get_weather(self, city, country, unit):
        """Return dict with 'text', 'icon', 'mode' for animation, and 'citylabel'"""
        try:
            q = f"{city},{country}" if country else city
            params = {"q": q, "appid": API_KEY, "units": unit}
            r = requests.get(f"{BASE_URL}/weather", params=params, timeout=10)
            data = r.json()

            if r.status_code == 200:
                temp = data["main"]["temp"]
                feels = data["main"].get("feels_like", temp)
                weather = data["weather"][0]["description"].capitalize()
                humidity = data["main"]["humidity"]
                wind_speed = data["wind"]["speed"]
                icon_code = data["weather"][0]["icon"]
                country_code = data["sys"].get("country", "")
                sunrise = datetime.datetime.fromtimestamp(data["sys"]["sunrise"]).strftime("%H:%M")
                sunset = datetime.datetime.fromtimestamp(data["sys"]["sunset"]).strftime("%H:%M")
                unit_symbol = "°C" if unit == "metric" else "°F"

                # icon
                icon_url = f"http://openweathermap.org/img/wn/{icon_code}@2x.png"
                icon = None
                try:
                    icon_data = requests.get(icon_url, timeout=8).content
                    icon = ImageTk.PhotoImage(Image.open(BytesIO(icon_data)).resize((110, 110)))
                except:
                    pass

                # pick animation mode
                mode = "sun"
                lc = weather.lower()
                if "rain" in lc or "drizzle" in lc or "thunder" in lc:
                    mode = "rain"
                elif "snow" in lc:
                    mode = "snow"

                text = (f"{q}  🌍 ({country_code})\n"
                        f"🌡 {temp}{unit_symbol} (feels {feels}{unit_symbol})\n"
                        f"☁ {weather}\n"
                        f"💧 {humidity}%   💨 {wind_speed} m/s\n"
                        f"🌅 {sunrise}   🌇 {sunset}")
                return {"ok": True, "text": text, "icon": icon, "mode": mode, "city_key": q}
            elif r.status_code == 401:
                return {"ok": False, "error": "Invalid or inactive API key. Please activate your key."}
            elif r.status_code == 404:
                return {"ok": False, "error": f"City '{city}' not found."}
            else:
                return {"ok": False, "error": data.get("message", "Unable to fetch weather")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _update_today(self, weather, unit):
        # Update history
        if "city_key" in weather and weather["ok"]:
            ck = weather["city_key"].split(",")[0].strip()
            if ck not in self.search_history:
                self.search_history.insert(0, ck)
                if len(self.search_history) > HISTORY_MAX:
                    self.search_history.pop()

        # Update UI
        self.show_page(self.today_frame)
        self.today_text_label.config(text="")
        if weather.get("icon"):
            self.today_icon_label.config(image=weather["icon"])
            self.today_icon_label.image = weather["icon"]
        else:
            self.today_icon_label.config(image="")
            self.today_icon_label.image = None

        # Start animation
        self.anim_canvas.update_idletasks()
        self.anim.start(weather["mode"] if weather.get("mode") else "sun")

        # Typewriter effect
        txt = weather["text"] if weather.get("ok") else f"❌ {weather.get('error', 'Unknown error')}"
        def type_in(i=0):
            if i <= len(txt):
                self.today_text_label.config(text=txt[:i])
                self.today_frame.after(10, lambda: type_in(i+1))
        type_in()

    def load_forecast(self):
        # switch to loading
        self.show_page(self.loading_frame)
        city = self.city_entry.get().strip()
        country = self.country_entry.get().strip()
        unit = "metric" if self.unit_var.get() == "Celsius" else "imperial"

        def work():
            data = self._get_forecast(city, country, unit)
            self.root.after(0, lambda: self._update_forecast(data, unit))
        threading.Thread(target=work, daemon=True).start()

    def _get_forecast(self, city, country, unit):
        try:
            q = f"{city},{country}" if country else city
            params = {"q": q, "appid": API_KEY, "units": unit}
            r = requests.get(f"{BASE_URL}/forecast", params=params, timeout=12)
            data = r.json()
            if r.status_code != 200:
                return {"ok": False, "error": data.get("message", "Unable to fetch forecast")}

            # reduce to 5 days (one point per day at ~12:00 if possible)
            buckets = {}
            for it in data["list"]:
                dt = datetime.datetime.fromtimestamp(it["dt"])
                key = dt.strftime("%Y-%m-%d")
                # prefer times around midday
                score = abs(dt.hour - 12)
                if key not in buckets or score < buckets[key]["score"]:
                    buckets[key] = {
                        "score": score,
                        "temp": it["main"]["temp"],
                        "desc": it["weather"][0]["description"].capitalize(),
                        "icon": it["weather"][0]["icon"],
                        "date": dt.date()
                    }
            days = list(sorted(buckets.values(), key=lambda x: x["date"]))[:5]
            # preload icons
            for d in days:
                try:
                    icon_data = requests.get(f"http://openweathermap.org/img/wn/{d['icon']}@2x.png", timeout=8).content
                    d["imgtk"] = ImageTk.PhotoImage(Image.open(BytesIO(icon_data)).resize((64, 64)))
                except:
                    d["imgtk"] = None
            return {"ok": True, "days": days}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _update_forecast(self, data, unit):
        self.show_page(self.forecast_frame)
        for w in self.cards_row.winfo_children(): w.destroy()

        if not data.get("ok"):
            tk.Label(self.forecast_frame, text=f"❌ {data.get('error','Error')}",
                     fg="red", bg=self.bg_color, font=("Arial", 12)).pack()
            return

        unit_symbol = "°C" if unit == "metric" else "°F"

        # Cards
        for d in data["days"]:
            card = tk.Frame(self.cards_row, bg="#1e1e1e", padx=10, pady=8)
            if d["imgtk"]:
                tk.Label(card, image=d["imgtk"], bg="#1e1e1e").pack()
                card.image = d["imgtk"]
            tk.Label(card, text=d["date"].strftime("%a %d %b"), fg="cyan", bg="#1e1e1e",
                     font=("Arial", 11, "bold")).pack()
            tk.Label(card, text=f"{round(d['temp'])}{unit_symbol}\n{d['desc']}",
                     fg="white", bg="#1e1e1e", font=("Arial", 10)).pack()
            card.pack(side="left", padx=8, pady=6)

        # Chart
        self.ax.clear()
        xs = [d["date"].strftime("%d %b") for d in data["days"]]
        ys = [d["temp"] for d in data["days"]]
        self.ax.plot(xs, ys, marker="o")
        self.ax.set_title("Temperature Trend (next 5 days)")
        self.ax.set_xlabel("Date")
        self.ax.set_ylabel(f"Temp ({unit_symbol})")
        self.ax.grid(True, linestyle="--", alpha=0.3)
        self.canvas_mpl.draw()

    def load_history(self):
        self.show_page(self.history_frame)
        for w in self.history_list.winfo_children(): w.destroy()
        if not self.search_history:
            tk.Label(self.history_list, text="No searches yet.", fg="white", bg=self.bg_color).pack()
            return
        for city in self.search_history:
            tb.Button(self.history_list, text=city, bootstyle="info-outline",
                      command=lambda c=city: self._search_from_button(c)).pack(pady=4)

    def _search_from_button(self, city):
        self.city_entry.delete(0, "end")
        self.city_entry.insert(0, city)
        self.start_weather()

    def load_favorites_page(self):
        self.show_page(self.favorites_frame)
        for w in self.fav_list.winfo_children(): w.destroy()
        if not self.favorites:
            tk.Label(self.fav_list, text="No favorites yet.", fg="white", bg=self.bg_color).pack()
            return
        for city in self.favorites:
            row = tk.Frame(self.fav_list, bg=self.bg_color)
            row.pack(pady=3)
            tb.Button(row, text=city, bootstyle="warning-outline",
                      command=lambda c=city: self._search_from_button(c)).pack(side="left", padx=6)
            tb.Button(row, text="🗑 Remove", bootstyle="danger-outline",
                      command=lambda c=city: self._remove_favorite(c)).pack(side="left", padx=6)

    def save_current_favorite(self):
        city = self.city_entry.get().strip()
        if not city: return
        if city not in self.favorites:
            self.favorites.insert(0, city)
            save_favorites(self.favorites)
            messagebox.showinfo("Saved", f"'{city}' added to favorites.", parent=self.root)
        else:
            messagebox.showinfo("Info", f"'{city}' is already in favorites.", parent=self.root)

    def _remove_favorite(self, city):
        if city in self.favorites:
            self.favorites.remove(city)
            save_favorites(self.favorites)
            self.load_favorites_page()

# ---- Run App ----
if __name__ == "__main__":
    # Auto-select theme at start; Window is created in WeatherApp
    root = tb.Window(themename="superhero")
    app = WeatherApp(root)
    root.mainloop()
