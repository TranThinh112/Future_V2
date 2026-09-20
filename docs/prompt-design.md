# Prompt design
Each agent must receive a sanitized market snapshot only and return the strict `AgentDecision` schema. Invalid, incomplete, conflicting, or stale input must produce HOLD.
