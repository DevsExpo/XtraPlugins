# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import urllib.parse
from typing import Optional, List, Dict, Any
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


async def _fetch_freedict(word: str) -> Optional[Dict[str, Any]]:
    """Fetch formal definition and phonetics from Free Dictionary API."""
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(url)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list) and len(data) > 0:
                return data[0]
    return None


async def _fetch_urban(word: str) -> Optional[Dict[str, Any]]:
    """Fetch slang definitions from Urban Dictionary API."""
    url = f"https://api.urbandictionary.com/v0/define?term={urllib.parse.quote(word)}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(url)
        if res.status_code == 200:
            data = res.json()
            items = data.get("list", [])
            if items:
                return items[0]
    return None


async def _fetch_rhymes(word: str, limit: int = 20) -> List[str]:
    """Fetch rhyming words using Datamuse API."""
    url = f"https://api.datamuse.com/words?rel_rhy={urllib.parse.quote(word)}&max={limit}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(url)
        if res.status_code == 200:
            return [item.get("word") for item in res.json() if "word" in item]
    return []


async def _fetch_synonyms(word: str, limit: int = 15) -> List[str]:
    """Fetch synonyms using Datamuse API."""
    url = f"https://api.datamuse.com/words?rel_syn={urllib.parse.quote(word)}&max={limit}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(url)
        if res.status_code == 200:
            return [item.get("word") for item in res.json() if "word" in item]
    return []


@Friday.register_on_cmd(
    ["dict", "define", "dictionary"],
    cmd_help={
        "help": "Lookup word definition, IPA phonetics, and examples across formal or slang providers.",
        "example": "dict serendipity\ndict -urban rizz\ndict -audio ephemeral\ndict -rhyme light",
    },
    requires_input=True,
)
async def dictionary_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for dictionary lookups.")

    raw = m.user_input.strip()
    with_audio = "-audio" in raw or "-voice" in raw
    if "-audio" in raw:
        raw = raw.replace("-audio", "").strip()
    if "-voice" in raw:
        raw = raw.replace("-voice", "").strip()

    is_urban = "-urban" in raw
    if "-urban" in raw:
        raw = raw.replace("-urban", "").strip()

    is_rhyme = "-rhyme" in raw
    if "-rhyme" in raw:
        raw = raw.replace("-rhyme", "").strip()

    if is_rhyme:
        return await rhyme_search(c, m)
    if is_urban:
        return await urban_search(c, m)

    word = raw.strip()
    if not word:
        return await m.handle_message("❌ Please provide a word to look up.")

    msg = await m.handle_message(f"📖 Searching dictionary for <b>{word}</b>...")

    try:
        data = await _fetch_freedict(word)
        if not data:
            # Fallback to Urban Dictionary if formal lookup is empty
            urban_item = await _fetch_urban(word)
            if urban_item:
                definition = urban_item.get("definition", "").replace("[", "").replace("]", "")
                example = urban_item.get("example", "").replace("[", "").replace("]", "")
                report = (
                    f"📖 <b>Urban Slang Result:</b> <code>{word}</code>\n\n"
                    f"<b>Definition:</b>\n{definition[:1200]}\n\n"
                    f'<b>Example:</b>\n<i>"{example[:600]}"</i>\n\n'
                    f"👍 {urban_item.get('thumbs_up', 0)} | 👎 {urban_item.get('thumbs_down', 0)}"
                )
                return await msg.edit_msg(report)
            return await msg.edit_msg(f"🤷‍♂️ No dictionary definition found for <code>{word}</code>.")

        # Parse formal dictionary
        phonetic = data.get("phonetic") or ""
        phonetics_list = data.get("phonetics", [])
        audio_url = None

        for p in phonetics_list:
            if not phonetic and p.get("text"):
                phonetic = p.get("text")
            if not audio_url and p.get("audio"):
                audio_url = p.get("audio")

        meanings = data.get("meanings", [])
        sections = []

        all_synonyms = []
        for m_item in meanings[:3]:
            pos = m_item.get("partOfSpeech", "general").capitalize()
            defs = m_item.get("definitions", [])
            lines = []
            for i, d in enumerate(defs[:2], 1):
                d_text = d.get("definition", "")
                ex_text = d.get("example")
                entry = f"  <b>{i}.</b> {d_text}"
                if ex_text:
                    entry += f'\n     <i>Example: "{ex_text}"</i>'
                lines.append(entry)

            syns = m_item.get("synonyms", [])
            if syns and isinstance(syns, list):
                all_synonyms.extend(syns[:4])

            sections.append(f"<b>[{pos}]</b>\n" + "\n".join(lines))

        deduped_synonyms = [str(s) for s in dict.fromkeys(all_synonyms) if s][:8]
        synonym_str = f"\n\n<b>• Synonyms:</b> {', '.join(deduped_synonyms)}" if deduped_synonyms else ""
        phonetic_str = f" <i>/{phonetic}/</i>" if phonetic else ""

        report = (
            f"📚 <b>Word:</b> <code>{word.capitalize()}</code>{phonetic_str}\n\n" + "\n\n".join(sections) + synonym_str
        )

        await msg.edit_msg(report)

        # Send pronunciation audio if available and requested
        if (with_audio or "-audio" in m.user_input) and audio_url:
            try:
                os.makedirs("temp/xtra_dict", exist_ok=True)
                audio_file = os.path.join("temp/xtra_dict", f"pronounce_{word}.mp3")
                async with httpx.AsyncClient(timeout=15.0) as dl_client:
                    ares = await dl_client.get(audio_url)
                    if ares.status_code == 200:
                        with open(audio_file, "wb") as f:
                            f.write(ares.content)
                        target_chat = m.chat_id or getattr(m.chat, "id", None)
                        await c.send_file(
                            target_chat,
                            audio_file,
                            voice_note=True,
                            caption=f"🔊 Pronunciation for <b>{word}</b>",
                            reply_to=m.id,
                        )
                        if os.path.exists(audio_file):
                            os.remove(audio_file)
            except Exception:
                pass
    except Exception as e:
        await msg.edit_msg(f"❌ Dictionary error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["urban", "slang"],
    cmd_help={
        "help": "Lookup slang, cultural terms, and meme definitions on Urban Dictionary.",
        "example": "urban skibidi\nurban cap",
    },
    requires_input=True,
)
async def urban_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    word = m.user_input.replace("-urban", "").strip()
    msg = await m.handle_message(f"🏙️ Searching Urban Dictionary for <b>{word}</b>...")

    try:
        item = await _fetch_urban(word)
        if not item:
            return await msg.edit_msg(f"🤷‍♂️ No Urban Dictionary definition found for <code>{word}</code>.")

        def_text = item.get("definition", "").replace("[", "").replace("]", "")
        example_text = item.get("example", "").replace("[", "").replace("]", "")
        thumbs_up = item.get("thumbs_up", 0)
        thumbs_down = item.get("thumbs_down", 0)
        author = item.get("author", "Urbanite")

        report = (
            f"🏙️ <b>Urban Dictionary:</b> <code>{word}</code>\n\n"
            f"<b>Definition:</b>\n{def_text[:1200]}\n\n"
            f'<b>Example:</b>\n<i>"{example_text[:500]}"</i>\n\n'
            f"👍 <b>{thumbs_up}</b> | 👎 <b>{thumbs_down}</b> • <i>By {author}</i>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Urban Dictionary error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["rhyme", "rhymes"],
    cmd_help={
        "help": "Find words that rhyme with the given word using rhyming linguistics database.",
        "example": "rhyme rhyme\nrhyme dream",
    },
    requires_input=True,
)
async def rhyme_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    word = m.user_input.replace("-rhyme", "").strip()
    msg = await m.handle_message(f"🎵 Finding rhymes for <b>{word}</b>...")

    try:
        rhymes = await _fetch_rhymes(word, limit=30)
        if not rhymes:
            return await msg.edit_msg(f"🤷‍♂️ No rhyming words found for <code>{word}</code>.")

        rhyme_pills = ", ".join([f"<code>{r}</code>" for r in rhymes])
        report = (
            f'🎵 <b>Words that Rhyme with "{word.capitalize()}":</b>\n\n'
            f"{rhyme_pills}\n\n"
            f"<i>Found {len(rhymes)} rhyming pairs.</i>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Rhyme lookup error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["synonyms", "syn", "thesaurus"],
    cmd_help={
        "help": "Find synonyms and alternative vocabulary for any word.",
        "example": "synonyms exquisite",
    },
    requires_input=True,
)
async def synonym_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    word = m.user_input.strip()
    msg = await m.handle_message(f"📖 Searching synonyms for <b>{word}</b>...")

    try:
        syns = await _fetch_synonyms(word, limit=20)
        if not syns:
            return await msg.edit_msg(f"🤷‍♂️ No synonyms found for <code>{word}</code>.")

        pills = ", ".join([f"<code>{s}</code>" for s in syns])
        report = (
            f'📖 <b>Thesaurus Synonyms for "{word.capitalize()}":</b>\n\n'
            f"{pills}\n\n"
            f"<i>Total alternative terms: {len(syns)}</i>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Synonym error: <code>{e}</code>")
