"""
core/regex_utils.py
───────────────────
Semua logika regex, normalisasi teks, dan pembuatan pola mutasi spam.

Modul ini adalah satu-satunya sumber kebenaran untuk:
  - Normalisasi & leet-speak                   → _normalize_leet, _normalize_strip, simplify
  - Matching regex dengan dual normalisasi      → match_with_leet
  - Parse sintaks user ke regex murni           → parse_simple_regex
  - Pipeline pembersihan teks spam              → pipeline_pembersihan
  - Generasi mutasi liar kata                   → generate_kandidat_mutasi_liar
  - Penyaringan 50% identity                    → saring_dengan_ambang_batas_50
  - Pembangunan interlock regex grup            → build_group_interlock
  - Mutasi panel/display (bridge nexus)         → generate_all_mutations
"""

import re
import unicodedata
from pyrogram.enums import MessageEntityType


# ─── Tabel Leetspeak (sumber kebenaran tunggal) ───────────────────────────────
LEET_MAP: dict[str, str] = {
    "0": "o", "1": "i", "3": "e", "4": "a",
    "5": "s", "6": "g", "7": "t", "8": "b",
    "9": "g", "@": "a",
}

# Alias private untuk kompatibilitas mundur
_LEET = LEET_MAP

# Leet map khusus untuk pipeline_pembersihan (angka → huruf, tanpa simbol)
_LEET_ANGKA: dict[str, str] = {
    k: v for k, v in LEET_MAP.items() if k.isdigit()
}


# ═════════════════════════════════════════════════════════════════════════════
#  BAGIAN 1 — parse_simple_regex (sintaks &&, |, (*))
# ═════════════════════════════════════════════════════════════════════════════

def _term_to_regex(term: str) -> str:
    r"""
    Konversi satu term (bisa dengan wildcard (*)) ke regex.

    Aturan:
      - "(*)" di awal/tengah/akhir → \w* (wildcard satu kata)
      - term kosong atau hanya "(*)" → raise ValueError
      - spasi dalam term → diperbolehkan (cocok frasa literal)

    Contoh:
      "togel"          → r"\btogel\b"
      "(*)nge"         → r"\b\w*nge\b"
      "jshh(*)hsh"     → r"\bjshh\w*hsh\b"
    """
    stripped = term.replace("(*)", "").strip()
    if not stripped:
        raise ValueError(f"Term kosong atau hanya wildcard: '{term}'")

    parts     = [re.escape(p) for p in term.split("(*)")]
    term_body = r"\w*".join(parts)
    return rf"\b{term_body}\b"


def parse_simple_regex(text: str) -> str:
    r"""
    Konversi sintaks mudah (&&, |, (*)) menjadi regex murni.

    Operator:
      |   → OR antara grup (prioritas terendah)
      &&  → AND semua term dalam satu grup (semua harus ada, urutan bebas)
      (*) → wildcard: cocok 0 atau lebih karakter kata di posisi itu

    Contoh:
      "togel"              → r"\btogel\b"
      "jual && akun"       → r"^(?=.*\bjual\b)(?=.*\bakun\b)"
      "promo | diskon"     → r"(\bpromo\b|\bdiskon\b)"

    Raises:
      ValueError jika ada term kosong, hanya (*), atau input kosong.
    """
    text = text.strip()
    if not text:
        raise ValueError("Input pola tidak boleh kosong.")

    or_groups = [g.strip() for g in text.split("|")]
    parsed_or_groups = []

    for group in or_groups:
        group = group.strip()
        if not group:
            raise ValueError("Ada grup OR yang kosong (dua '|' berurutan atau '|' di tepi).")

        terms = [t.strip() for t in group.split("&&")]
        parsed_terms = []

        for term in terms:
            term = term.strip()
            if not term:
                raise ValueError(f"Ada term AND yang kosong di grup: '{group}'")
            parsed_terms.append(_term_to_regex(term))

        if len(parsed_terms) > 1:
            lookaheads = "".join(f"(?=.*{pt})" for pt in parsed_terms)
            parsed_or_groups.append(f"(?:^{lookaheads})")
        else:
            parsed_or_groups.append(parsed_terms[0])

    if len(parsed_or_groups) > 1:
        return "(?:" + "|".join(parsed_or_groups) + ")"
    return parsed_or_groups[0]


# ═════════════════════════════════════════════════════════════════════════════
#  BAGIAN 2 — Normalisasi & Matching (dual normalization)
# ═════════════════════════════════════════════════════════════════════════════

def _normalize_leet(text: str) -> str:
    """
    Versi A: replace SEMUA angka ke huruf leet, lalu hapus sisa digit, lalu dedup.
    Cocok untuk: "5An63e3e" → "sange"
    """
    text = unicodedata.normalize("NFKC", text).lower()
    for ch, rep in LEET_MAP.items():
        text = text.replace(ch, rep)
    text = re.sub(r"\d", "", text)
    text = re.sub(r"([a-z])\1+", r"\1", text)
    return text


def _normalize_strip(text: str) -> str:
    """
    Versi B: hapus SEMUA digit dulu (anggap noise), lalu leet simbol (@), lalu dedup.
    Cocok untuk: "saaaaaang5eeeee33eee" → "sange"
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"\d", "", text)
    for ch, rep in LEET_MAP.items():
        if not ch.isdigit():
            text = text.replace(ch, rep)
    text = re.sub(r"([a-z])\1+", r"\1", text)
    return text


def get_normalized_variants(text: str) -> tuple[str, str]:
    """
    Kembalikan dua versi normalisasi untuk dual matching.
    Returns: (leet_version, strip_version)

    Spasi dan tanda baca TETAP ada di kedua versi (tidak seperti simplify()).
    """
    return _normalize_leet(text), _normalize_strip(text)


def match_with_leet(pattern: re.Pattern, text: str) -> bool:
    """
    Cocokkan compiled regex pattern ke teks dengan dual normalization.
    Return True jika salah satu versi match.
    """
    norm_leet, norm_strip = get_normalized_variants(text)
    return bool(pattern.search(norm_leet) or pattern.search(norm_strip))


def simplify(text: str) -> str:
    """
    Normalisasi agresif: NFKC → lower → leet → dedup → HAPUS non a-z (termasuk spasi).
    Dipakai untuk deteksi pesan duplikat lokal & global.
    JANGAN dipakai untuk regex matching (spasi dihapus = AND logic rusak).
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    for ch, rep in LEET_MAP.items():
        text = text.replace(ch, rep)
    text = re.sub(r"(.)\1+", r"\1", text)
    return re.sub(r"[^a-z]", "", text)


def normalize_input(text: str) -> str:
    """NFKC + lowercase. Dipakai sebelum simpan pola ke DB."""
    return unicodedata.normalize("NFKC", text).lower()


def remove_mentions_for_regex(message) -> str:
    """Hapus @mention dari teks agar regex tidak salah tembak username."""
    content = message.text or message.caption or ""
    if not message.entities:
        return unicodedata.normalize("NFKC", content)

    clean = content
    for ent in sorted(message.entities, key=lambda x: x.offset, reverse=True):
        if ent.type in (MessageEntityType.MENTION, MessageEntityType.TEXT_MENTION):
            start = ent.offset
            end   = ent.offset + ent.length
            clean = clean[:start] + (" " * ent.length) + clean[end:]

    return unicodedata.normalize("NFKC", clean)


# ═════════════════════════════════════════════════════════════════════════════
#  BAGIAN 3 — Pipeline Pembersihan Teks Spam
# ═════════════════════════════════════════════════════════════════════════════

def normalisasi_font(teks: str) -> str:
    """NFKD normalize + hapus combining characters (font hias, dll)."""
    teks_normal = unicodedata.normalize("NFKD", teks)
    return "".join([c for c in teks_normal if not unicodedata.combining(c)])


def convert_angka_ke_huruf(teks: str) -> str:
    """Konversi angka leet-speak ke huruf (hanya digit, tanpa simbol)."""
    return "".join(_LEET_ANGKA.get(char, char) for char in teks)


def hapus_karakter_berulang_total(teks: str) -> str:
    """Hapus karakter non-spasi berulang: 'aaaaaa' → 'a'."""
    return re.sub(r"([^\s])\1+", r"\1", teks)


def pipeline_pembersihan(teks_mentah: str) -> str:
    """
    Pipeline lengkap pembersihan teks spam sebelum diproses AI/regex.

    Langkah:
      1. Lowercase
      2. Normalisasi font (NFKD, hapus combining)
      3. Konversi angka → huruf (leet)
      4. Hapus karakter berulang
      5. Hapus tanda baca
      6. Normalisasi whitespace
    """
    if not teks_mentah:
        return ""
    t = teks_mentah.lower()
    t = normalisasi_font(t)
    t = convert_angka_ke_huruf(t)
    t = hapus_karakter_berulang_total(t)
    t = re.sub(r"[^\w\s]", "", t)
    return " ".join(t.split())


# ═════════════════════════════════════════════════════════════════════════════
#  BAGIAN 4 — Generasi Mutasi Kata (50% Identity Engine)
# ═════════════════════════════════════════════════════════════════════════════

def hitung_karakter_asli_dalam_pola(pola_regex: str) -> int:
    """Hitung karakter literal (bukan metachar) dalam pola regex."""
    bersih = (pola_regex
              .replace("\\b", "")
              .replace(".*", "")
              .replace("\\w*", "")
              .replace("\\", ""))
    return len(bersih)


def saring_dengan_ambang_batas_50(kata_asli: str, daftar_kandidat: list) -> list:
    """
    Filter kandidat: hanya lolos jika paling tidak 50% karakter asli terwakili.
    Fallback ke pola literal jika semua kandidat gugur.
    """
    syarat_minimal = (len(kata_asli) + 1) // 2
    lolos = [p for p in daftar_kandidat if hitung_karakter_asli_dalam_pola(p) >= syarat_minimal]
    if not lolos:
        lolos = [f"\\b{re.escape(kata_asli)}\\b"]
    return lolos


def generate_kandidat_mutasi_liar(kata: str) -> list:
    """
    Generate semua kemungkinan pola regex mutasi dari satu kata.

    Menghasilkan pola prefix/suffix/infix dengan wildcard (.*) lalu
    disaring dengan saring_dengan_ambang_batas_50 agar akurasi terjaga.

    Return: list[str] — daftar pola regex siap pakai.
    """
    if not kata:
        return []
    kandidat = [f"\\b{re.escape(kata)}\\b"]
    n = len(kata)

    if n < 3:
        kandidat.append(f"\\b{re.escape(kata[0])}.*")
        kandidat.append(f".*{re.escape(kata[-1])}\\b")
        return list(set(kandidat))

    for i in range(1, n):
        kandidat.append(f"\\b{re.escape(kata[:i])}.*")
        kandidat.append(f".*{re.escape(kata[i:])}\\b")

    for i in range(1, n):
        for j in range(i + 1, n + 1):
            if i == 1 and j == n:
                kandidat.append(f"\\b{re.escape(kata[0])}.*{re.escape(kata[-1])}\\b")
            elif j < n:
                kandidat.append(f"\\b{re.escape(kata[:i])}.*{re.escape(kata[j:])}\\b")

    return saring_dengan_ambang_batas_50(kata, list(set(kandidat)))


def generate_all_mutations(pola: str) -> tuple[list, str]:
    """
    Jembatan panel Nexus — hasilkan tampilan mutasi dan regex gabungan.

    Dipakai oleh handlers_fsm.py untuk visualisasi saat owner menambah
    Owner Regex. Menggunakan LEET_MAP extended (termasuk b, c, l, s, z, dll)
    karena tujuannya menampilkan semua kemungkinan karakter pengganti,
    bukan sekadar normalisasi.

    Return:
      (mutasi_display: list[tuple[char, pola]], raw_joined: str)
    """
    pola = pola.strip().lower().replace(" ", "")

    # Extended leet untuk keperluan display/visualisasi
    _LEET_DISPLAY: dict[str, str] = {
        "a": r"[aA4@]", "b": r"[bB8]", "c": r"[cC]", "e": r"[eE3]",
        "g": r"[gG69]", "i": r"[iI1!l|]", "l": r"[lL1|iI]", "o": r"[oO0]",
        "s": r"[sS5$]", "t": r"[tT7]", "z": r"[zZ2]",
    }

    mutasi_display = []
    regex_parts    = []

    for char in pola:
        if char in _LEET_DISPLAY:
            r_pola = _LEET_DISPLAY[char]
            regex_parts.append(r_pola + r"+")
            mutasi_display.append((char, r_pola))
        elif char.isalpha() or char.isdigit():
            r_pola = f"[{char.lower()}{char.upper()}]"
            regex_parts.append(r_pola + r"+")
            mutasi_display.append((char, r_pola))
        else:
            esc_char = re.escape(char)
            regex_parts.append(esc_char + r"*")
            mutasi_display.append((char, esc_char))

    raw_joined = r"".join(regex_parts)
    return mutasi_display, raw_joined


# ═════════════════════════════════════════════════════════════════════════════
#  BAGIAN 5 — Interlock Regex Builder (untuk grup & owner)
# ═════════════════════════════════════════════════════════════════════════════

def build_group_interlock(raw_input: str) -> tuple[str, list[str]]:
    """
    Parse 'kata | kata | kata' dan rakit interlock pola ala nexus owner.

    Setiap kata diproses pipeline_pembersihan lalu generate_kandidat_mutasi_liar
    menghasilkan lookahead (?=.*(alternasi_mutasi)).
    Pola akhir adalah gabungan semua lookahead — cocok hanya jika SEMUA kata
    hadir sekaligus (AND semantics).

    Return:
      (pola_regex: str, kata_bersih_list: list[str])

    Raises:
      ValueError jika input kosong atau tidak menghasilkan kata valid.
    """
    kata_list = [k.strip() for k in raw_input.split("|") if k.strip()]
    if not kata_list:
        raise ValueError("Input kosong — minimal satu kata.")

    lookaheads       = []
    kata_bersih_list = []

    for kata in kata_list:
        kata_clean = pipeline_pembersihan(kata)
        if not kata_clean:
            continue
        kata_token = kata_clean.split()[0]
        mutasi     = generate_kandidat_mutasi_liar(kata_token)
        if mutasi:
            alts = "|".join(mutasi)
            lookaheads.append(f"(?=.*({alts}))")
            kata_bersih_list.append(kata_token)

    if not lookaheads:
        raise ValueError("Semua kata kosong atau tidak menghasilkan mutasi valid.")

    pola = "".join(lookaheads)
    return pola, kata_bersih_list


# Alias untuk kompatibilitas mundur (regex_group.py & handlers_fsm.py lama)
_build_group_interlock = build_group_interlock
