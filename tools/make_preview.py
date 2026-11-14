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
SP = ZoneInfo("America/Sao_Paulo")
# Arrival in São Paulo: Nov 27, 07:00 Brasília time.
ARRIVAL = datetime(2026, 11, 27, 7, 0, tzinfo=SP)
ARRIVAL_LABEL = ("27 de novembro", "sexta-feira, às 7h da manhã")
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

    to_arrival = max(timedelta(0), ARRIVAL - now)
    return {"remain": remain, "work": work, "nights": nights, "done": remain == timedelta(0),
            "to_arrival": to_arrival, "arrived": to_arrival == timedelta(0)}


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
    """Recipient-facing card: how long until Matheus arrives in São Paulo."""
    W, H = 1200, 630
    img = gradient_bg(W, H)
    d = ImageDraw.Draw(img)
    f = lambda name, size: ImageFont.truetype(str(FONTS / f"InterDisplay-{name}.otf"), size)
    ink, muted, green, blue = (16, 40, 58), (93, 115, 133), (18, 148, 90), (43, 111, 214)

    # Headline
    head = "O Matheus tá chegando!"
    if r["arrived"]:
        head = "O Matheus chegou!"
    elif r["done"]:
        head = "O Matheus já está voando!"
    d.text((70, 52), head, font=f("ExtraBold", 60), fill=ink)

    # Left: arrival date, big
    d.text((72, 168), "CHEGA EM SÃO PAULO", font=f("Bold", 28), fill=green)
    date_txt, when_txt = ARRIVAL_LABEL
    size = 92
    while d.textlength(date_txt, font=f("ExtraBold", size)) > 600:
        size -= 4
    d.text((68, 205), date_txt, font=f("ExtraBold", size), fill=green)
    d.text((72, 318), when_txt, font=f("SemiBold", 36), fill=ink)

    route = "Seattle  →  São Paulo"
    rf = f("Bold", 30)
    rw = d.textlength(route, font=rf)
    d.rounded_rectangle((70, 392, 70 + rw + 56, 452), radius=30, fill=ink)
    d.text((98, 422), route, font=rf, fill=(255, 255, 255), anchor="lm")

    # Right: countdown cards
    x0, cw = 720, 410
    secs = r["to_arrival"].total_seconds()
    hours = int(secs // 3600)
    days = int(secs // 86400)
    if r["arrived"]:
        cards = [("Bem-vindo!", "de volta ao Brasil", green)]
    else:
        cards = [
            (f"{hours}h", "até a chegada", blue),
            (("hoje!" if days == 0 else f"{days} {'dia' if days == 1 else 'dias'}"), "faltando", green),
        ]
    ch, gap = (180, 24) if len(cards) == 2 else (384, 0)
    y = 160
    for value, label, color in cards:
        d.rounded_rectangle((x0, y, x0 + cw, y + ch), radius=30, fill=(255, 255, 255), outline=(225, 233, 241), width=2)
        vs = 96 if len(cards) == 2 else 80
        while d.textlength(value, font=f("ExtraBold", vs)) > cw - 50:
            vs -= 4
        d.text((x0 + cw / 2, y + ch / 2 - 22), value, font=f("ExtraBold", vs), fill=color, anchor="mm")
        d.text((x0 + cw / 2, y + ch - 36), label, font=f("Bold", 30), fill=muted, anchor="mm")
        y += ch + gap

    local = now.astimezone(TZ)
    stamp = f"Atualizado {WEEKDAYS_PT[local.weekday()]}, {local.day} {MONTHS_PT[local.month - 1]} · {local:%H}h (horário de Seattle)"
    d.text((72, 540), stamp, font=f("SemiBold", 24), fill=muted, anchor="lm")

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
