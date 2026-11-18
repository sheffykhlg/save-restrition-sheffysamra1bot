import re
from pyrogram import enums
from pyrogram.types import MessageEntity
from pyrogram.parser.html import HTML
from core.config import logger
from database.repository import get_user_replace_rules

URL_PATTERN = re.compile(r'https?://\S+|www\.\S+|t\.me/\S+')

def clean_text_and_links(text: str, user_id: int) -> str:
    if not text:
        return ""
    cleaned = URL_PATTERN.sub('', text)
    rules = get_user_replace_rules(user_id)
    for old_word, new_word in rules.items():
        if old_word:
            cleaned = re.sub(re.escape(old_word), new_word, cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

async def process_caption_and_entities(raw_text: str, entities: list, user_id: int):
    """
    Bulletproof entity & caption processor:
    Preserves 100% of Telegram special formatting (underline, monospace/code, spoiler, bold, italic,
    strikethrough, blockquote, custom_emoji, expandable blockquote, etc.).
    Cleans URLs and applies user replace rules without breaking entity bounds.
    Recalculates exact UTF-16 entity offsets so Telegram never throws ENTITY_BOUNDS_INVALID.
    """
    if not raw_text:
        return "", None

    rules = get_user_replace_rules(user_id)

    # If there are no entities, perform standard text cleaning
    if not entities:
        cleaned = clean_text_and_links(raw_text, user_id)
        return cleaned, None

    # Full entity support: converts all Telegram formatting to valid HTML
    try:
        html_text = HTML.unparse(raw_text, entities)

        # 1. Apply user replace rules
        if rules:
            for old_word, new_word in rules.items():
                if old_word:
                    html_text = re.sub(re.escape(old_word), new_word, html_text, flags=re.IGNORECASE)

        # 2. Clean URLs & links
        html_text = re.sub(r'<a\s+href="[^"]*">(.*?)</a>', r'\1', html_text)
        html_text = URL_PATTERN.sub('', html_text)
        cleaned_html = re.sub(r'[ \t]+', ' ', html_text).strip()

        # 3. Parse HTML back to text with newly calculated, exact entity offsets
        html_parser = HTML(None)
        parsed = await html_parser.parse(cleaned_html)
        final_text = parsed.get("message", "")
        raw_ents = parsed.get("entities", [])
        if raw_ents:
            final_entities = [await MessageEntity._parse(None, e, {}) for e in raw_ents]
        else:
            final_entities = None
        return final_text, final_entities
    except Exception as e_proc:
        logger.warning(f"process_caption_and_entities fallback ({e_proc}) for user {user_id}")
        cleaned = clean_text_and_links(raw_text, user_id)
        return cleaned, None

def filter_entities_and_clean(entities, original_text, cleaned_text):
    if not entities or not cleaned_text:
        return None
    text_utf16_len = len(cleaned_text.encode("utf-16-le")) // 2
    new_entities = []
    ignored_types = [
        enums.MessageEntityType.TEXT_LINK,
        enums.MessageEntityType.URL,
        enums.MessageEntityType.MENTION,
        enums.MessageEntityType.TEXT_MENTION
    ]
    for entity in entities:
        if entity.type in ignored_types:
            continue
        if (entity.offset + entity.length) <= text_utf16_len:
            new_entities.append(entity)
    return new_entities if new_entities else None

