"""A conservative extra keyword branch; semantic retrieval keeps the full question."""
import re


def keyword_question(query: str) -> str:
    value = query.strip()
    value = re.sub(r"^(?:请问|请帮我|请)[，,\s]*", "", value)
    value = re.sub(r"^(?:如何(?:理解|认识|解释|看待)?|怎样(?:理解|认识|解释)?|什么是|为什么)[，,\s]*", "", value)
    value = re.sub(r"^(?:what is|what are|how does|how do|why does|why do)\s+", "", value, flags=re.I)
    value = re.sub(r"[？?。\s]+$", "", value)
    return value if len(value) >= 2 else query.strip()
