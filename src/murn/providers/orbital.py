class OrbitalProvider:
    """Placeholder for the native Orbital <-> murn. bridge.

    Keep the browser behind a provider boundary so Chromium-specific code does not
    leak into the agent core. When Orbital exposes its local API/WebSocket bridge,
    implement methods such as open_url(), page_context(), click(), type_text(),
    tabs() and screenshot() here, then register only the safe actions as tools.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url

    @property
    def configured(self) -> bool:
        return bool(self.base_url)
