"""HTTP request contracts."""

from pydantic import BaseModel, ConfigDict, Field


class RadioRequest(BaseModel):
    """Radio transcript supplied for local classification."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2_000)


class AgentAdviceRequest(BaseModel):
    """Optional natural-language race-director request."""

    model_config = ConfigDict(extra="forbid")

    lap: int = Field(gt=0)
    driver_id: str = Field(min_length=1, max_length=128)
    question: str = Field(default="What should we do next?", min_length=1, max_length=1_000)
