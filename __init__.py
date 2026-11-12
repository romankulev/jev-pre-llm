"""jev-pre-llm directory-plugin entrypoint: the plugin exposes one ``register(ctx)``."""

__all__ = ["register"]


def __getattr__(name: str):
    if name == "register":
        from .jpl.runtime import register

        return register
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
