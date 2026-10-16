import os, json, re, math, random, urllib.request
from playwright.sync_api import sync_playwright

URL = ("https://www.amazon.eg/-/en/tez/browse)
MIN_DISCOUNT = 40
TOPIC = os.environ["NTFY_TOPIC"]
TEST = os.environ.get("TEST") == "1"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

VIEWPORTS = [(1366, 768), (1440, 900), (1536, 864), (1920, 1080), (1280, 720)]

JS = """
els => els.map(a => {
  const uniq = x => new Set([...x.querySelectorAll('a[href*="/dp/"]')]
                  .map(l => l.href.split('?')[0])).size;
  let n = a.parentElement, t = '';
  while (n && uniq(n) <= 1) {
    if (/\\d+\\s*%/.test(n.innerText)) { t = n.innerText; break; }
    n = n.parentElement;
  }
  return [a.href, a.innerText, t];
})
"""

# ---------- سلوك بشري ----------
pos = {"x": 0, "y": 0}


def pause(a=0.4, b=1.6):
    """وقفة عشوائية بالمللي ثانية"""
    return random.randint(int(a * 1000), int(b * 1000))


def human_move(pg, x1, y1):
    """حركة ماوس منحنية بسرعة متغيرة (مش خط مستقيم)"""
    x0, y0 = pos["x"], pos["y"]
    cx1 = x0 + (x1 - x0) * random.uniform(0.2, 0.5) + random.randint(-120, 120)
    cy1 = y0 + (y1 - y0) * random.uniform(0.2, 0.5) + random.randint(-120, 120)
    cx2 = x0 + (x1 - x0) * random.uniform(0.5, 0.8) + random.randint(-80, 80)
    cy2 = y0 + (y1 - y0) * random.uniform(0.5, 0.8) + random.randint(-80, 80)
    steps = random.randint(25, 55)
    for i in range(1, steps + 1):
        t = i / steps
        t = t * t * (3 - 2 * t)  # بطيء في الأول والآخر وسريع في النص
        x = ((1-t)**3 * x0 + 3*(1-t)**2*t * cx1 + 3*(1-t)*t**2 * cx2 + t**3 * x1)
        y = ((1-t)**3 * y0 + 3*(1-t)**2*t * cy1 + 3*(1-t)*t**2 * cy2 + t**3 * y1)
        pg.mouse.move(x, y)
        pg.wait_for_timeout(random.randint(4, 18))
    pos["x"], pos["y"] = x1, y1


def wander(pg, vw, vh):
    """لف بالماوس في أماكن عشوائية"""
    for _ in range(random.randint(1, 3)):
        human_move(pg, random.randint(50, vw - 50), random.randint(80, vh - 80))
        pg.wait_for_timeout(pause(0.2, 0.9))


def hover_random_product(pg, vw, vh):
    """يقف بالماوس على منتج عشوائي كأنه بيقرأه"""
    try:
        links = pg.query_selector_all('a[href*="/dp/"]')
        random.shuffle(links)
        for el in links[:8]:
            box = el.bounding_box()
            if box and 0 < box["y"] < vh - 40 and box["width"] > 40:
                human_move(
                    pg,
                    box["x"] + box["width"] * random.uniform(0.2, 0.8),
                    box["y"] + box["height"] * random.uniform(0.2, 0.8),
                )
                pg.wait_for_timeout(pause(0.6, 2.2))
                return
    except Exception:
        pass


def human_scroll(pg, vw, vh):
    """سكرول على دفعات صغيرة، مع وقفات ورجوع لفوق أحيانًا"""
    for _ in range(random.randint(5, 9)):
        for _ in range(random.randint(3, 6)):
            pg.mouse.wheel(0, random.randint(70, 180))
            pg.wait_for_timeout(random.randint(30, 120))
        pg.wait_for_timeout(pause(0.7, 2.5))  # بيقرأ
        r = random.random()
        if r < 0.25:
            hover_random_product(pg, vw, vh)
        elif r < 0.40:
            pg.mouse.wheel(0, -random.randint(100, 350))  # يرجع شوية لفوق
            pg.wait_for_timeout(pause(0.5, 1.4))
        elif r < 0.55:
            wander(pg, vw, vh)


# ---------- الإشعارات ----------
def notify(title, msg):
    req = urllib.request.Request(
        "https://ntfy.sh/" + TOPIC,
        data=msg.encode("utf-8"),
        headers={"Title": title, "Priority": "high"},
    )
    urllib.request.urlopen(req, timeout=30)


items = []
page_title = ""
body = ""
error = ""

with sync_playwright() as p:
    vw, vh = random.choice(VIEWPORTS)
    b = p.chromium.launch(
        args=["--disable-blink-features=AutomationControlled"]
    )
    ctx = b.new_context(
        user_agent=UA,
        locale="en-EG",
        timezone_id="Africa/Cairo",
        viewport={"width": vw, "height": vh},
        extra_http_headers={"Accept-Language": "en-EG,en;q=0.9,ar;q=0.8"},
    )
    ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    pg = ctx.new_page()
    pos["x"], pos["y"] = random.randint(100, vw - 100), random.randint(100, vh - 100)
    try:
        pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(pause(3, 6))
        wander(pg, vw, vh)
        human_scroll(pg, vw, vh)
        pg.wait_for_selector('a[href*="/dp/"]', timeout=15000)
        # رجوع لأول الصفحة وتقليب أخير
        pg.mouse.wheel(0, -random.randint(800, 2000))
        pg.wait_for_timeout(pause(1, 2.5))
    except Exception as e:
        error = str(e)[:150]
    try:
        items = pg.eval_on_selector_all('a[href*="/dp/"]', JS)
        page_title = pg.title()
        body = " ".join(pg.inner_text("body").split())[:200]
        if "captcha" in body.lower() or "robot" in body.lower():
            error += " | captcha"
    except Exception as e:
        error += " | " + str(e)[:100]
    b.close()

found = {}
deals = {}
for href, link_text, card_text in items:
    key = href.split("?")[0]
    text = " ".join((link_text or card_text).split())[:80]
    found[key] = text
    pcts = [int(x) for x in re.findall(r"(\d{1,2})\s*%", card_text)]
    if pcts and max(pcts) >= MIN_DISCOUNT:
        deals[key] = "%d%% - %s" % (max(pcts), text)

try:
    seen = set(json.load(open("seen.json")))
except Exception:
    seen = set()

new = {h: t for h, t in deals.items() if h not in seen}

if new:
    lines = [t + "\n" + h for h, t in list(new.items())[:10]]
    notify("Amazon Egypt %d percent off" % MIN_DISCOUNT, "\n\n".join(lines))
elif TEST:
    notify(
        "Amazon test",
        "products: %d | deals: %d | title: %s | error: %s | text: %s"
        % (len(found), len(deals), page_title, error, body),
    )

if not error:
    json.dump(sorted(deals), open("seen.json", "w"))
