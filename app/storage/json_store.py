"""Atomic local checkpoint store for paper-mode restart recovery."""
import json
import os
import tempfile


class JsonStore:
    def __init__(self, path="paper_state.json"): self.path=path
    def save(self, value):
        fd,tmp=tempfile.mkstemp(dir=".",prefix="paper_state_")
        with os.fdopen(fd,"w",encoding="utf-8") as f: json.dump(value,f)
        os.replace(tmp,self.path)
    def load(self, default):
        try:
            with open(self.path,encoding="utf-8") as f: return json.load(f)
        except (FileNotFoundError,json.JSONDecodeError): return default
