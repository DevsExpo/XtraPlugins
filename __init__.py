# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

"""
XtraPlugins Suite 2.0 for Friday
---------------------------------
Comprehensive modular toolbox structured into 5 specialized categories:

1. Media (media/):
   - carbon_tools: Carbon-style syntax code snapshot generator with macOS themes.
   - collage_tools: Multi-image grid, row, column, and polaroid collage synthesizer.
   - image_tools: Resize, crop, blur, invert, circle, watermark, compress, convert, logo maker.
   - ocr_tools: Multi-language optical text recognition, local Tesseract, and custom AI OCR endpoints.
   - quote_tools: Telegram-style speech bubble sticker and photo generator (@QuotLy alternative).
   - scanner_tools: CamScanner-style document thresholding and contrast enhancer.
   - video_tools: Trim, audio extraction (MP3), mute, video-to-GIF, media info inspection.
   - ytdl_tools: YouTube/web video downloader, 320kbps MP3 audio extractor, search, and technical inspection.

2. Search & OSINT (search_osint/):
   - ctf_tools: Media forensics, EXIF metadata, GPS, magic signatures, steganography alerts, flag finder.
   - dict_tools: Multi-provider formal & slang dictionary, Datamuse rhymes, synonyms, pronunciation audio.
   - github_tools: Repository details, user dossiers, and starred project inspection.
   - ip_tools: Deep IP geolocation, ASN, ISP, VPN/Proxy detection, and reverse DNS.
   - movie_tools: IMDb movie, TV, and anime search with plots, ratings, cast, posters, and trending feed.
   - osint_tools: 10+ social network username reconnaissance, crt.sh subdomains, disposable email check.
   - search_tools: Google / DuckDuckGo web search with pagination, image fetcher, multi-engine reverse search.
   - wiki_tools: Multi-language Wikipedia articles, thumbnail previews, and random article discovery.

3. Utilities (utilities/):
   - country_tools: 250-country dataset by name, calling code (+91, +1), or ISO codes.
   - ifsc_tools: Indian bank IFSC lookup via Razorpay, branch addresses, and reverse search.
   - math_tools: Safe AST mathematical expression solver with step-by-step calculus & algebra.
   - pdf_tools: Multi-page text-to-PDF, image-to-PDF converter, and PDF document inspector.
   - qr_tools: High-contrast QR code generator with styles, QR code scanner & decoder.
   - smart_utilities: Real-time currency conversion, secure password generator, hashes, base64, mock identities.
   - tempmail_tools: Instant disposable email mailboxes via mail.tm with live OTP verification reader.

4. System (system/):
   - archive_tools: Safe zip, zip-slip protected unzip, archive listing, tar.gz.
   - drive_tools: Google Drive public link inspector and direct streaming downloader.
   - nightmode_tools: Automated group quiet hours scheduler using AsyncIOScheduler with admin check.
   - transfer_tools: Direct streaming downloader & uploader with ASCII progress bars.

5. Lifestyle (lifestyle/):
   - calendar_tools: ASCII calendar, countdown, date difference calculator, world time.
   - maps_tools: OpenStreetMap geocoding, static map preview images, OSRM turn-by-turn driving directions, pins.
   - shazam_tools: Audio song & track fingerprint recognition.
   - shopping_tools: Multi-marketplace product price search and comparison.
   - todo_tools: Database-backed persistent task manager with visual checkboxes and priorities.
   - translate_tools: Multi-language instant translation.
   - travel_tools: Train schedules, live railway status, and flight tracking.
   - weather_tools: Live meteorological weather conditions, forecasts, and UV/humidity metrics.
   - web_tools: Webpage screenshots, DNS DoH resolution, RDAP/WHOIS, URL unshortener.

6. Bot-Based (botbased/):
   - fban: Multi-federation ban (.fban), unban (.unfban), federation registry (.fadd, .frem, .flist), and Rose bot converser.
"""

__version__ = "2.1.0"

