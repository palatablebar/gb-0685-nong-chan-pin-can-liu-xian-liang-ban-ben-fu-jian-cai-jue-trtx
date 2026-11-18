from app.modules.m2_mapping.rules import normalize


def execute(state, saved_aliases=None):
    return normalize(state, saved_aliases)
