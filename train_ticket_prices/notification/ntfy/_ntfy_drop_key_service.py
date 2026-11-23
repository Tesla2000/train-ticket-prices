from pydantic import BaseModel, ConfigDict


class NtfyDropKeyService(BaseModel):
    """Identifies a drop by its route and departure, read back from sent text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Origin, arrow, destination, departure date and departure time.
    key_tokens: int = 5

    def extract_key(self, line: str) -> str:
        """Route and departure only, so a train listed by one source is not repeated by another."""
        return " ".join(line.split()[: self.key_tokens])
