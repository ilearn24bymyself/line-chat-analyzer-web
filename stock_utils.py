import re
import json
import os

# Common years to exclude
EXCLUDED_YEARS = set(str(y) for y in range(1980, 2100))

class StockExtractor:
    def __init__(self, whitelist_path="stock_codes.json"):
        self.whitelist_path = whitelist_path
        self.whitelist = {}        # code -> name
        self.name_to_code = {}     # name -> code (for Chinese name recognition)
        self.load_whitelist()

    def load_whitelist(self):
        if os.path.exists(self.whitelist_path):
            try:
                with open(self.whitelist_path, "r", encoding="utf-8") as f:
                    self.whitelist = json.load(f)
                # Build reverse lookup: Chinese name -> code
                self.name_to_code = {v: k for k, v in self.whitelist.items()}
            except Exception:
                self.whitelist = {}
                self.name_to_code = {}

    def extract(self, text):
        """Extract stock codes from text (supports 4-digit codes AND Chinese names)."""
        if not text:
            return []

        found = set()

        # 1. 4-digit numeric code extraction
        candidates = re.findall(r'(?<!\d|\.)(\d{4})(?!\d|\.\d|:)', text)
        for code in candidates:
            if code in EXCLUDED_YEARS:
                continue
            if self.whitelist:
                if code in self.whitelist:
                    found.add(code)
            else:
                found.add(code)

        # 2. Chinese name recognition (whitelist-based, longest match first)
        if self.name_to_code:
            # Sort by name length descending to match longer names first (e.g. 台積電 before 台積)
            for name, code in sorted(self.name_to_code.items(), key=lambda x: -len(x[0])):
                if len(name) >= 2 and name in text:
                    found.add(code)

        return list(found)

    def extract_names(self, text):
        """Return matched Chinese stock names from text."""
        if not text or not self.name_to_code:
            return []
        matched = []
        for name in sorted(self.name_to_code.keys(), key=lambda x: -len(x)):
            if len(name) >= 2 and name in text:
                matched.append(name)
        return matched

    def get_name(self, code):
        return self.whitelist.get(code, "")

    def get_code_by_name(self, name):
        return self.name_to_code.get(name, "")
