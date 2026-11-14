"""Generate the link-preview image (preview.png) with a live countdown snapshot.

Mirrors the countdown math in index.html using the default settings, and bumps
the og:image cache-busting query in index.html so link previews pick up the new image.
Run hourly by .github/workflows/preview.yml.
"""
import re
from datetime import datetime, date, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "tools" / "fonts"
TZ = ZoneInfo("America/Los_Angeles")

# Same defaults as the page.
FLIGHT = datetime(2026, 11, 26, 7, 0, tzinfo=TZ)
LAST_WORK_DAY = date(2026, 11, 25)
WORK_BLOCKS = [(time(9, 0), time(12, 0)), (time(13, 0), time(18, 0))]
BEDTIME = time(23, 0)
DAYS_OFF: set[date] = set()

WEEKDAYS_PT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=TZ)


def compute(now: datetime) -> dict:
    remain = max(timedelta(0), FLIGHT - now)
    today = now.astimezone(TZ).date()

    work = timedelta(0)
    d = today
    last = min(LAST_WORK_DAY, FLIGHT.date())
    while d <= last:
        if d.weekday() < 5 and d not in DAYS_OFF:
            for a, b in WORK_BLOCKS:
                s, e = max(at(d, a), now), min(at(d, b), FLIGHT)
                if e > s:
                    work += e - s
        d += timedelta(days=1)

    nights = 0
    d = today
    while d < FLIGHT.date():
        t = at(d, BEDTIME)
        if now < t < FLIGHT:
            nights += 1
        d += timedelta(days=1)

    return {"remain": remain, "work": work, "nights": nights, "done": remain == timedelta(0)}


def gradient_bg(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    px = img.load()
    top, mid, bot = (207, 232, 255), (244, 248, 252), (255, 236, 210)
    for y in range(h):
        t = y / (h - 1)
        a, b, u = (top, mid, t / 0.55) if t < 0.55 else (mid, bot, (t - 0.55) / 0.45)
        c = tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))
        for x in range(w):
            px[x, y] = c
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((800, -240, 1440, 400), fill=150)
    mask = mask.filter(ImageFilter.GaussianBlur(90))
    return Image.composite(Image.new("RGB", (w, h), (255, 208, 130)), img, mask)


def render(now: datetime, r: dict, out: Path) -> None:
    W, H = 1200, 630
    img = gradient_bg(W, H)
    d = ImageDraw.Draw(img)
    f = lambda name, size: ImageFont.truetype(str(FONTS / f"InterDisplay-{name}.otf"), size)
    ink, muted, green, blue = (16, 40, 58), (93, 115, 133), (18, 148, 90), (43, 111, 214)

    d.text((70, 58), "Tá chegando, ", font=f("ExtraBold", 64), fill=ink)
    d.text((70 + d.textlength("Tá chegando, ", font=f("ExtraBold", 64)), 58), "Matheus!", font=f("ExtraBold", 64), fill=green)
    d.text((72, 140), "Contagem regressiva para a viagem ao Brasil", font=f("SemiBold", 30), fill=muted)

    if r["done"]:
        d.text((70, 250), "Chegou o dia!", font=f("ExtraBold", 110), fill=green)
        d.text((74, 390), "Boa viagem! O Brasil te espera.", font=f("SemiBold", 42), fill=ink)
    else:
        total_h = int(r["remain"].total_seconds() // 3600)
        work_min = int(-(-r["work"].total_seconds() // 60))  # ceil to the minute, like the page
        cards = [
            (f"{total_h}h", "até o voo", blue),
            (f"{work_min // 60}h{work_min % 60:02d}" if work_min % 60 else f"{work_min // 60}h", "de trabalho", green),
            (str(r["nights"]), "noite" if r["nights"] == 1 else "noites", (196, 140, 0)),
        ]
        x, y, cw, ch, gap = 70, 222, 336, 230, 26
        for value, label, color in cards:
            d.rounded_rectangle((x, y, x + cw, y + ch), radius=30, fill=(255, 255, 255), outline=(225, 233, 241), width=2)
            size = 104
            while d.textlength(value, font=f("ExtraBold", size)) > cw - 50:
                size -= 4
            vf = f("ExtraBold", size)
            d.text((x + cw / 2, y + 100), value, font=vf, fill=color, anchor="mm")
            d.text((x + cw / 2, y + 180), label, font=f("Bold", 34), fill=muted, anchor="mm")
            x += cw + gap

    local = now.astimezone(TZ)
    stamp = f"Atualizado {WEEKDAYS_PT[local.weekday()]}, {local.day} {MONTHS_PT[local.month - 1]} · {local:%H}h (Seattle)"
    pill = "Voo 26 nov · Seattle → Brasil"
    pf = f("Bold", 26)
    pw = d.textlength(pill, font=pf)
    d.rounded_rectangle((70, 500, 70 + pw + 48, 552), radius=26, fill=ink)
    d.text((94, 526), pill, font=pf, fill=(255, 255, 255), anchor="lm")
    d.text((W - 70, 526), stamp, font=f("SemiBold", 24), fill=muted, anchor="rm")

    d.rectangle((0, H - 14, W // 2, H), fill=green)
    d.rectangle((W // 2, H - 14, W, H), fill=(242, 183, 5))
    img.save(out, optimize=True)


def bump_og_version(now: datetime) -> None:
    """Point og:image/twitter:image at preview.png?v=<hour> so previews re-fetch the new image."""
    index = ROOT / "index.html"
    html = index.read_text(encoding="utf-8")
    v = now.astimezone(TZ).strftime("%Y%m%d%H")
    html = re.sub(r"preview\.png(\?v=\d+)?\"", f'preview.png?v={v}"', html)
    index.write_text(html, encoding="utf-8")


def main() -> None:
    now = datetime.now(TZ)
    r = compute(now)
    render(now, r, ROOT / "preview.png")
    bump_og_version(now)
    print(f"remain={r['remain']} work={r['work']} nights={r['nights']} done={r['done']}")


if __name__ == "__main__":
    main()
