import os, io, math
import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.utils import ImageReader

PLAYER_URL = "https://funaki678-at.github.io/hitster-player"
DPI    = 150
PX     = int(66 / 25.4 * DPI)
COLS   = 3
ROWS   = 4
GAP_MM = 0

DECADE_COLORS = {
    1950: ("#311B92", "#4527A0"),
    1960: ("#BF360C", "#E64A19"),
    1970: ("#E65100", "#F57C00"),
    1980: ("#880E4F", "#C2185B"),
    1990: ("#004D40", "#00695C"),
    2000: ("#0D47A1", "#1565C0"),
    2010: ("#1B5E20", "#2E7D32"),
    2020: ("#B71C1C", "#D32F2F"),
}

FONT_PATHS = {
    "bold":    ["C:/Windows/Fonts/arialbd.ttf",  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "italic":  ["C:/Windows/Fonts/ariali.ttf",   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"],
    "regular": ["C:/Windows/Fonts/arial.ttf",    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}

def load_font(style, size):
    for path in FONT_PATHS[style]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def get_decade_colors(year):
    decade = (year // 10) * 10
    return DECADE_COLORS.get(decade, ("#212121", "#424242"))

def draw_gradient(img, color1, color2):
    draw = ImageDraw.Draw(img)
    r1,g1,b1 = int(color1[1:3],16),int(color1[3:5],16),int(color1[5:7],16)
    r2,g2,b2 = int(color2[1:3],16),int(color2[3:5],16),int(color2[5:7],16)
    for y in range(PX):
        t = y / PX
        draw.line([(0,y),(PX,y)],
                  fill=(int(r1+(r2-r1)*t), int(g1+(g2-g1)*t), int(b1+(b2-b1)*t)))

def wrap_text(text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        if font.getbbox(test)[2] <= max_width:
            current = test
        else:
            if current: lines.append(current)
            current = word
    if current: lines.append(current)
    return lines

def draw_multiline(d, lines, font, cx, y, fill, spacing=1.2):
    lh = int((font.getbbox("Ag")[3] - font.getbbox("Ag")[1]) * spacing)
    for line in lines:
        d.text((cx, y), line, font=font, fill=fill, anchor="mt")
        y += lh
    return y

def make_back(track):
    c1, c2 = get_decade_colors(int(track["year"]))
    img = Image.new("RGB", (PX, PX))
    draw_gradient(img, c1, c2)
    d   = ImageDraw.Draw(img)
    pad = int(PX * 0.07)
    WHITE = (255, 255, 255)
    max_w = PX - 2 * pad

    f_artist   = load_font("bold",    int(PX * 0.090))
    f_year     = load_font("bold",    int(PX * 0.30))
    f_title    = load_font("italic",  int(PX * 0.078))
    f_playlist = load_font("regular", int(PX * 0.050))

    artist_lines = wrap_text(track["artists"], f_artist, max_w)[:2]
    draw_multiline(d, artist_lines, f_artist, PX//2, pad + int(PX*0.02), WHITE, 1.15)

    d.text((PX//2, PX//2 - int(PX*0.04)), track["year"],
           font=f_year, fill=WHITE, anchor="mm")

    title_lines = wrap_text(track["name"], f_title, max_w)[:3]
    title_lh = int((f_title.getbbox("Ag")[3] - f_title.getbbox("Ag")[1]) * 1.2)
    title_y  = PX - pad - int(PX*0.07) - len(title_lines) * title_lh
    draw_multiline(d, title_lines, f_title, PX//2, title_y, WHITE, 1.2)

    pl = track["playlist"]
    if len(pl) > 32: pl = pl[:30] + "…"
    d.text((PX//2, PX - pad + int(PX*0.01)), pl,
           font=f_playlist, fill=(255,255,255,160), anchor="mb")

    return img

def make_front(track):
    c1, c2 = get_decade_colors(int(track["year"]))
    img = Image.new("RGB", (PX, PX))
    draw_gradient(img, c1, c2)

    url = f"{PLAYER_URL}?track={track['track_id']}"
    qr  = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                         box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img  = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_size = int(PX * 0.80)
    qr_img  = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
    img.paste(qr_img, ((PX-qr_size)//2, (PX-qr_size)//2))

    return img

def pil_to_rl(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)

def _draw_cut_lines(cv, start_x, start_y, total_w, total_h, card_pt, gap_pt):
    page_w, page_h = A4
    cv.setStrokeColorRGB(0.5, 0.5, 0.5)
    cv.setLineWidth(0.25)
    for c in range(COLS+1):
        lx = start_x + c * card_pt  # gap_pt is 0, kept for clarity
        cv.line(lx, 0, lx, page_h)
    for r in range(ROWS+1):
        ly = start_y + r * card_pt
        cv.line(0, ly, page_w, ly)

def generate_pdfs_from_tracks(tracks, out_dir, progress_callback=None):
    page_w, page_h = A4
    card_pt = 66 * mm
    gap_pt  = GAP_MM * mm
    total_w = COLS * card_pt + (COLS-1) * gap_pt
    total_h = ROWS * card_pt + (ROWS-1) * gap_pt
    start_x = (page_w - total_w) / 2
    start_y = (page_h - total_h) / 2
    per_page = COLS * ROWS

    front_path  = os.path.join(out_dir, "shitster_vorderseiten.pdf")
    back_path   = os.path.join(out_dir, "shitster_rueckseiten.pdf")
    duplex_path = os.path.join(out_dir, "shitster_duplex.pdf")

    front_cv  = pdfcanvas.Canvas(front_path,  pagesize=A4)
    back_cv   = pdfcanvas.Canvas(back_path,   pagesize=A4)
    duplex_cv = pdfcanvas.Canvas(duplex_path, pagesize=A4)

    pages = math.ceil(len(tracks) / per_page)
    total = len(tracks)

    # Pre-render all card images so we can reuse them for the duplex PDF
    # (avoids regenerating QR codes / PIL images twice)
    rendered = []  # list of (front_rl, back_rl) per track slot

    for page in range(pages):
        page_tracks = tracks[page*per_page:(page+1)*per_page]
        while len(page_tracks) < per_page:
            page_tracks.append(None)

        page_rendered = []
        for pos, track in enumerate(page_tracks):
            if track is None:
                page_rendered.append(None)
                continue
            col = pos % COLS
            row = pos // COLS
            x_f = start_x + col * (card_pt + gap_pt)
            y_f = start_y + (ROWS-1-row) * (card_pt + gap_pt)
            x_b = start_x + (COLS-1-col) * (card_pt + gap_pt)

            front_rl = pil_to_rl(make_front(track))
            back_rl  = pil_to_rl(make_back(track))
            page_rendered.append((col, row, x_f, y_f, x_b, front_rl, back_rl))

            front_cv.drawImage(front_rl, x_f, y_f, card_pt, card_pt)
            back_cv.drawImage( back_rl,  x_b, y_f, card_pt, card_pt)

            if progress_callback:
                progress_callback(page * per_page + pos + 1, total)

        rendered.append(page_rendered)

        for cv in (front_cv, back_cv):
            _draw_cut_lines(cv, start_x, start_y, total_w, total_h, card_pt, gap_pt)
            cv.showPage()

    # Build duplex PDF: front page then back page alternating
    for page_rendered in rendered:
        # Front page
        for slot in page_rendered:
            if slot is None: continue
            col, row, x_f, y_f, x_b, front_rl, back_rl = slot
            duplex_cv.drawImage(front_rl, x_f, y_f, card_pt, card_pt)
        _draw_cut_lines(duplex_cv, start_x, start_y, total_w, total_h, card_pt, gap_pt)
        duplex_cv.showPage()

        # Back page (mirrored columns, same as back_cv)
        for slot in page_rendered:
            if slot is None: continue
            col, row, x_f, y_f, x_b, front_rl, back_rl = slot
            duplex_cv.drawImage(back_rl, x_b, y_f, card_pt, card_pt)
        _draw_cut_lines(duplex_cv, start_x, start_y, total_w, total_h, card_pt, gap_pt)
        duplex_cv.showPage()

    front_cv.save()
    back_cv.save()
    duplex_cv.save()
    return front_path, back_path, duplex_path

def get_tracks_from_playlist(sp, playlist_url):
    playlist_id = playlist_url.strip().split("/")[-1].split("?")[0]
    playlist    = sp.playlist(playlist_id)
    if "error" in playlist:
        raise Exception(f"Spotify Fehler: {playlist['error']}")
    name    = playlist["name"]
    tracks  = []
    results = playlist.get("tracks") or playlist.get("items")
    while results:
        for item in results["items"]:
            track = item.get("track") or item.get("item")
            if not track or track.get("id") is None: continue
            if track.get("type") != "track": continue
            tracks.append({
                "name":     track["name"],
                "artists":  ", ".join(a["name"] for a in track["artists"]),
                "year":     track["album"]["release_date"][:4],
                "track_id": track["id"],
                "playlist": name,
            })
        results = sp.next(results) if results.get("next") else None
    return tracks
