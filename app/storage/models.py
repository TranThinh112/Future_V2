"""Persistence contract; production deployments should map these records to PostgreSQL."""
from dataclasses import dataclass


@dataclass
class Event: kind:str; payload:dict; timestamp_ms:int
