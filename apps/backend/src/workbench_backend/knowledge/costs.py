"""Small disclosed content estimates shared by knowledge views and selections."""

TOKEN_ESTIMATE_METHOD = "Content estimate (3 characters/token); excludes prompt wrappers; not tokenizer usage"


def content_token_estimate(content: str) -> int:
    return (len(content) + 2) // 3
