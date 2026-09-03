def clean_string(value: str) -> str:
    return value.replace("\u200f", "").strip("\r").strip("\n").strip()
