# 🚀 XtraPlugins v2.0

> **The Sovereign Utility, Media Synthesis, Deep OSINT & System Automation Suite for Friday**  
> Engineered with zero-dependency fallbacks, visual interactive responses, asynchronous scheduling, and modular subcategory packages.

[![Friday Compatible](https://img.shields.io/badge/Friday-v2.0_Plugin-007ACC.svg?style=flat-square)](https://github.com/FridaySoftware/Friday)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![Zero Key Architecture](https://img.shields.io/badge/Architecture-Zero_Key_Ready-10B981.svg?style=flat-square)](#)
[![Subcategories](https://img.shields.io/badge/Architecture-5_Modular_Domains-8B5CF6.svg?style=flat-square)](#)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-green.svg?style=flat-square)](LICENSE)

---

## 🧭 Subcategory Architecture

`XtraPlugins` is organized into 5 domain packages. Each directory includes isolated modular requirements:

```text
XtraPlugins/
├── 🎨 media/                  # Visual graphics, photo editing, quotes & document OCR
│   ├── carbon_tools.py        # Carbon-style code snippet graphics with macOS window styling
│   ├── collage_tools.py       # Multi-image grid, row, column & polaroid collage synthesizer
│   ├── image_tools.py         # Resizing, cropping, filters, watermarking, format conversion, logo maker
│   ├── ocr_tools.py           # Optical character recognition (Cloud + Local Tesseract + Self-Hosted AI)
│   ├── quote_tools.py         # Telegram chat bubble sticker/photo generator (@QuotLy alternative)
│   ├── scanner_tools.py       # CamScanner-style document thresholding and contrast enhancer
│   └── video_tools.py         # Trimming, MP3 audio extraction, audio muting, video-to-GIF, media info
│
├── 🔎 search_osint/           # Deep web research, security reconnaissance & media forensics
│   ├── ctf_tools.py           # EXIF inspection, GPS links, magic signatures, steganography alerts
│   ├── dict_tools.py          # Formal & slang definitions, rhymes, synonyms, voice audio playback
│   ├── github_tools.py        # User profiles, repositories, stars, commit trees & release downloads
│   ├── ip_tools.py            # Deep IP geolocation, ASN, ISP, VPN/Proxy threat detection, reverse DNS
│   ├── movie_tools.py         # IMDb movies/TV with plot synopses, ratings, cast, posters & trending feed
│   ├── osint_tools.py         # 10+ social network username scanner, crt.sh subdomains, disposable email
│   ├── search_tools.py        # Google / DuckDuckGo web search with pagination & reverse image matches
│   └── wiki_tools.py          # Multi-language Wikipedia articles, thumbnail previews & random discovery
│
├── 🧰 utilities/              # Precision daily utilities, documents & disposable tools
│   ├── country_tools.py       # 250-country dataset by name, calling code (+91, +1), or ISO codes
│   ├── ifsc_tools.py          # Indian bank IFSC lookup via Razorpay, branch addresses & reverse search
│   ├── math_tools.py          # Safe AST-based mathematical expression solver & step-by-step calculus
│   ├── pdf_tools.py           # Paginated text-to-PDF, image-to-PDF converter & PDF metadata inspector
│   ├── qr_tools.py            # High-contrast styled QR code generator & camera/file QR decoder
│   ├── smart_utilities.py     # Live FX currency conversion, password generator, hashes, mock identity
│   └── tempmail_tools.py      # Real disposable mailboxes via mail.tm with live OTP verification reader
│
├── ⚙️ system/                 # Automation, background tasks & file streaming
│   ├── archive_tools.py       # Zip, Zip-Slip safe extraction, archive manifest peek, tar.gz
│   ├── drive_tools.py         # Google Drive public link inspector and direct streaming downloader
│   ├── nightmode_tools.py     # Automated group quiet hours scheduler using AsyncIOScheduler
│   └── transfer_tools.py      # Streaming downloader & uploader with live visual ASCII progress bars
│
└── 🌿 lifestyle/              # Personal organization, travel, transit & physical world tracking
    ├── calendar_tools.py      # ASCII calendar, date countdown & difference calculator, UTC world time
    ├── maps_tools.py          # Static map previews, OSRM turn-by-turn driving directions, pins & distance
    ├── shazam_tools.py        # Song and audio track recognition from voice/video/audio clips
    ├── shopping_tools.py      # Multi-marketplace product price search and comparison across Amazon/eBay
    ├── todo_tools.py          # Database-backed task manager with visual checkboxes and priorities
    ├── translate_tools.py     # Fast multi-language translator without heavy dependencies
    ├── travel_tools.py        # Indian Railways live schedule & route, OpenSky flight tracker
    ├── weather_tools.py       # Live meteorological conditions, UV index, humidity & multi-day forecasts
    └── web_tools.py           # Webpage screenshots, Cloudflare DoH DNS, RDAP/WHOIS, URL unshortener
```

---

## ⚡ Quick Start & Installation

Install directly into Friday via the built-in package manager:

```text
.fpm_install https://github.com/<your_username>/XtraPlugins
```

### Modular Requirements Installation

Install only the subcategories you need, or install all at once:

```bash
# All-in-one installation
pip install -r XtraPlugins/media/requirements.txt
pip install -r XtraPlugins/search_osint/requirements.txt
pip install -r XtraPlugins/utilities/requirements.txt
pip install -r XtraPlugins/system/requirements.txt
pip install -r XtraPlugins/lifestyle/requirements.txt
```

---

## 📖 Feature & Command Reference

### 🎨 Media Synthesis & Graphics (`media/`)

| Command | Arguments | Flags / Options | Description |
|---|---|---|---|
| `.carbon` | `[code]` | `-theme [dracula\|nord\|monokai\|synthwave]`, `-title <fn>`, `-nolines` | Render a Carbon-style syntax highlighted code window. |
| `.carbonthemes`| — | — | List all available syntax window color schemes. |
| `.quote` | `[text]` | `-theme [dark\|light\|dracula\|synthwave\|emerald]`, `-sticker`, `-img` | Generate a Telegram chat bubble sticker or image (@QuotLy alternative). |
| `.quotethemes` | — | — | Display all available chat bubble color schemes. |
| `.collage` | — | `-layout [grid\|row\|column\|polaroid]`, `-bg [dark\|white\|rose]`, `-pad <px>` | Synthesize multiple replied photos into an elegant collage. |
| `.ocr` | — | `-l <lang>`, `-trans <lang>`, `-table`, `-clean`, `-tess`, `-custom` | Optical character recognition from photos/documents. |
| `.ocrset` | `<api_key>` | `default` | Save custom OCR.space key or restore free default. |
| `.ocrcustom` | `<endpoint>` | `[bearer_token]`, `off` | Route OCR to self-hosted AI models (Surya, PaddleOCR, vLLM). |
| `.ocrconfig` | — | — | Inspect active OCR engines, Tesseract status & settings. |
| `.iresize` | `<w>x<h>` | e.g. `512x512` | High-quality Lanczos photo resizing. |
| `.iblur` | `[radius]` | e.g. `10` | Gaussian blur filter. |
| `.iinvert` | — | — | Invert colors (negative photo effect). |
| `.icircle` | — | — | Crop photo into a circular avatar with transparency. |
| `.irotate` | `<angle>` | e.g. `90`, `180`, `270` | Rotate photo by specified angle. |
| `.icap` | `<text>` | — | Add banner caption overlay on image. |
| `.iwatermark` | `<text>` | — | Apply translucent diagonal security watermark. |
| `.iconvert` | `<format>` | `PNG`, `JPEG`, `WEBP`, `ICO` | Convert between visual formats. |
| `.ilogo` | `<title>` | `[subtitle]` | Generate stylized minimalist typography brand card. |
| `.scan` | — | `bw`, `magic` | CamScanner document thresholding & contrast enhancer. |
| `.trim` | `<start> <end>`| e.g. `00:05 00:20` | Fast lossless video trimming. |
| `.toaudio` | — | — | Extract high-bitrate MP3 audio from any video. |
| `.mute` | — | — | Strip all audio tracks from video. |
| `.togif` | — | — | Convert video clip to an animated Telegram GIF. |
| `.vinfo` | — | — | Inspect video resolution, bitrate, fps, and codecs. |

---

### 🔎 Search, Intelligence & OSINT (`search_osint/`)

| Command | Arguments | Flags / Options | Description |
|---|---|---|---|
| `.google` / `.g` | `<query>` | `-p <page>`, `-num <count>`, `-site <domain>` | Web search with snippets and page navigation. |
| `.img` | `<query>` | `-n <count>` (1-8) | Download and send web images directly into chat. |
| `.reverse` / `.ris` | — | (reply to photo) | Multi-engine visual lookup (Google Lens, Yandex, TinEye, SauceNAO). |
| `.wiki` | `<topic>` | `-es`, `-fr`, `-hi`, `-ru`, `-de` | Wikipedia summary with article photo and language flags. |
| `.wikirand` | `[lang_flag]` | e.g. `-es` | Discover a random fascinating Wikipedia article. |
| `.movie` / `.imdb` | `<title>` | — | IMDb ratings, plot synopses, cast, director, and poster. |
| `.trending` | — | — | Browse current box office and streaming trending titles. |
| `.github` | `<user[/repo]>` | — | Inspect GitHub repository stats, user bios, and stars. |
| `.ghstars` | `<user>` | — | View recently starred repositories of any user. |
| `.osint` | `<username>` | — | Check username availability across 10+ social platforms. |
| `.subdomains` | `<domain>` | — | Enumerate SSL certificate subdomains via crt.sh. |
| `.checkemail` | `<email>` | — | Check email validity and detect disposable inbox domains. |
| `.dict` | `<word>` | `-urban`, `-audio`, `-rhyme` | Formal definitions, IPA phonetics & pronunciation audio. |
| `.urban` | `<slang>` | — | Search Urban Dictionary slang definitions & vote counts. |
| `.rhyme` | `<word>` | — | Find rhyming words using Datamuse linguistic engine. |
| `.synonyms` | `<word>` | — | Thesaurus alternative terms and vocabulary builder. |
| `.ip` / `.iplookup` | `<ip/domain>` | — | Geolocation, ASN, ISP, VPN/Proxy check & reverse DNS. |
| `.myip` | — | — | Display bot host's public IP address and ISP. |
| `.ctf` / `.exif` | — | (reply to media) | Media forensics, EXIF metadata, GPS, magic signatures, hidden flag scanner. |

---

### ⚙️ System Automation & Group Control (`system/`)

| Command | Arguments | Flags / Options | Description |
|---|---|---|---|
| `.nightmode` | `<HH:MM> <HH:MM>` | `-tz <timezone>`, `-mode full\|media`, `-msg <alert>` | Automated quiet hours scheduler via `AsyncIOScheduler`. |
| `.nightoff` | — | — | Disable night mode and restore group chat permissions. |
| `.nightstatus` | — | — | View active night schedule, timezone, and next run times. |
| `.nightlock` | — | — | Manually lock chat permissions immediately (Admin). |
| `.nightunlock` | — | — | Manually unlock chat permissions immediately (Admin). |
| `.zip` | `<dir_path>` | — | Create compressed zip archive. |
| `.unzip` | — | (reply to archive) | Extract zip archive with Zip-Slip path traversal protection. |
| `.ziplist` | — | (reply to archive) | Peek archive contents without downloading or extracting. |
| `.gdrive` | `<url>` | — | Inspect file name, size, and download Google Drive links. |
| `.download` | `<url>` | — | Download web file with live ASCII progress bar. |
| `.upload` | `<path>` | — | Upload local server file to Telegram chat. |

---

### 🧰 Everyday Utilities & Security (`utilities/`)

| Command | Arguments | Description |
|---|---|---|
| `.tempmail` | — | Provision an instant disposable email inbox via `mail.tm`. |
| `.checkmail` | `[email]` | Read inbox messages and automatically extract verification OTP codes. |
| `.delmail` | — | Delete active disposable email mailbox. |
| `.country` | `<name/code>` | Country info by name, ISO code, or calling code (e.g. `+91`, `+1`). |
| `.ifsc` | `<code>` | Indian bank IFSC lookup via Razorpay with branch address & RTGS. |
| `.bank` | `<bank> \| <branch>`| Reverse search bank branch to obtain IFSC code. |
| `.qr` | `<content>` | Generate high-contrast styled QR code image. |
| `.readqr` | — | Scan and decode QR code from replied photo. |
| `.math` | `<expression>` | Safe AST evaluation with step-by-step calculus (`diff`, `integrate`). |
| `.topdf` | `<title> \| <text>` | Render paginated, styled PDF document from text. |
| `.imgtopdf` | — | Convert replied image to a standard PDF document. |
| `.pdfinfo` | — | Inspect PDF page count, metadata, title, author, and encryption. |
| `.currency` | `<amt> <from> <to>` | Real-time exchange rate conversion (e.g. `100 USD EUR`). |
| `.pass` | `[length]` | Cryptographically secure random password generator. |
| `.hash` | `<text>` | Generate MD5, SHA-1, SHA-256, and SHA-512 cryptographic digests. |
| `.b64e` / `.b64d` | `<text>` | Encode or decode Base64 strings. |
| `.fakeid` | — | Generate realistic synthetic persona for test accounts. |

---

### 🌿 Lifestyle & Transit (`lifestyle/`)

| Command | Arguments | Description |
|---|---|---|
| `.map` | `<location>` | OpenStreetMap geocoding with static map photo preview. |
| `.directions` | `<Origin> \| <Dest>` | Turn-by-turn driving route, distance, and duration via OSRM. |
| `.pin` | `<location/lat lon>` | Send native interactive Telegram location pin. |
| `.distance` | `<PointA> \| <PointB>` | Calculate straight-line geographic distance (km, miles, nmi). |
| `.todo` | `<task>` | Add task to MongoDB database with priority (`!high`). |
| `.todos` | — | Display interactive checklist with checkboxes (`[x]`, `[ ]`). |
| `.tododone` | `<id>` | Mark a task as completed. |
| `.todoclear` | — | Purge completed tasks from database. |
| `.weather` | `<city>` | Real-time temperature, humidity, wind, and conditions. |
| `.forecast` | `<city>` | 3-day meteorological forecast breakdown. |
| `.cal` | `[month] [year]` | Render month ASCII calendar with current date marker. |
| `.countdown` | `<YYYY-MM-DD>` | Calculate precise countdown in days, hours, and minutes. |
| `.worldtime` | `<city>` | Display current local time and timezone offset. |
| `.shazam` | — | Identify music track from replied voice note, audio, or video clip. |
| `.price` | `<item>` | Search and compare product pricing across marketplaces. |
| `.train` | `<number>` | Live Indian Railways schedule, route stations, and timings. |
| `.flight` | `<callsign>` | Real-time aircraft position, altitude, and velocity via OpenSky. |
| `.tr` | `<text>` | Instant multi-language translation (e.g. `tr es Hello friend`). |
| `.webshot` | `<url>` | Capture full webpage snapshot. |
| `.whois` | `<domain>` | Domain registration, registrar, dates, and nameservers. |
| `.dns` | `<domain>` | Cloudflare DNS over HTTPS record resolution. |
| `.unshort` | `<short_url>` | Trace redirects to expose destination link. |

---
