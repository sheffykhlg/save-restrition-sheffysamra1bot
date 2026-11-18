import re

LINK_REGEX = re.compile(r"(?:t\.me|telegram\.me|telegram\.dog)/(?:c/)?([^/?#]+)/(?:(\d+)/)?(\d+)")

def is_telegram_link_private(link: str) -> bool:
    if not link:
        return False
    if "/c/" in link:
        return True
    m = LINK_REGEX.search(link)
    if m:
        chat_id_part = m.group(1)
        if chat_id_part.isdigit() or chat_id_part.startswith("-100"):
            return True
    return False

def parse_telegram_link(link: str):
    """
    Parses any telegram message link (public, private, supergroup topic).
    Returns (chat_identifier, topic_id, message_id, is_private) or None.
    """
    m = LINK_REGEX.search(link)
    if not m:
        return None
    chat_identifier = m.group(1)
    topic_id = None
    if m.group(2):
        topic_id = int(m.group(2))
        message_id = int(m.group(3))
    else:
        message_id = int(m.group(3))

    if chat_identifier.isdigit():
        chat_identifier = int(f"-100{chat_identifier}")

    is_private = is_telegram_link_private(link) or isinstance(chat_identifier, int)
    return chat_identifier, topic_id, message_id, is_private

