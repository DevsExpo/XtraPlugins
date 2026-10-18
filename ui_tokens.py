# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
#
# Centralized UI & Emoji Tokens for XtraPlugins.
# Segregated from Main to keep extra plugin suites modular and independently styled.

from types import SimpleNamespace

# Common Extra Plugin Feedback
STATUS = SimpleNamespace(
    OK="✅",
    FAIL="❌",
    WARN="⚠️",
    INFO="ℹ️",
    BUSY="⏳",
    REFRESH="🔄",
    BULLET="•",
    TIP="💡",
    CLI="📖",
)

# Lifestyle: Calendar & Holidays
CALENDAR = SimpleNamespace(
    ICON="📅",
    PARTY="🎉",
    TODAY="🌟",
    TARGET="🗓",
    CLOCK="⌛",
    PIN="📌",
)

# Lifestyle: News & Information
NEWS = SimpleNamespace(
    ICON="📰",
    SIGNAL="📡",
    FLASH="⚡",
    TOP="🇮🇳",
    TECH="💻",
    BUSINESS="📈",
    SPORTS="🏏",
    WORLD="🌐",
    SCIENCE="🔬",
    ENTERTAINMENT="🎬",
)

# Lifestyle: Hotels, Travel & Stays
HOTEL = SimpleNamespace(
    ICON="🏨",
    LUXURY="💎",
    MID="🏨",
    BUDGET="🎒",
    LINK="🔗",
    MAP="📍",
    STAR="★",
)

# Lifestyle: Pomodoro Focus Timer
POMODORO = SimpleNamespace(
    TOMATO="🍅",
    WORK="🔥",
    BREAK="☕",
    LONG_BREAK="🏖",
    PAUSE="⏸",
    BELL="🔔",
    STATS="📊",
)

# Lifestyle: Todo Checklist
TODO = SimpleNamespace(
    LIST="📋",
    MEMO="📝",
    DONE="✅",
    PENDING="⬜",
    HIGH_PRIO="🔴",
    SWEEP="🧹",
)

# Search & OSINT Tokens
OSINT = SimpleNamespace(
    GLOBE="🌐",
    SEARCH="🔍",
    CAMERA="📸",
    LINK="🔗",
    PIN="📍",
    DNS="🌐",
    IP="📍",
)

# Media & Utilities Tokens
MEDIA = SimpleNamespace(
    CHART="📈",
    MUSIC="🎵",
    CUT="✂️",
    FILM="🎬",
    DOWNLOAD="⬇️",
)
