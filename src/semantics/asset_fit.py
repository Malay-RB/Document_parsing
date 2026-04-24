#asset_fit.py

import json
import pandas as pd


class NearbyContentLinker:
    """
    Reads a structured hierarchy JSON, finds children with nearby_content_ids,
    and appends the source child's asset onto each referenced child.
    """

    def __init__(self, input_path: str, output_path: str):
        self.input_path = input_path
        self.output_path = output_path
        self.records: list[dict] = []
        self._child_index: dict[str, dict] = {}  # id → child node

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def run(self) -> list[dict]:
        """Load → index → link → save → return."""
        self._load()
        self._build_index()
        self._link_nearby_assets()
        self._save()
        return self.records

    # ------------------------------------------------------------------ #
    # I/O
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        df = pd.read_json(self.input_path)
        self.records = df.to_dict(orient="records")

    def _save(self) -> None:
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(self.records, f, indent=2, ensure_ascii=False)
        print(f":white_check_mark: JSON saved → {self.output_path}")

    # ------------------------------------------------------------------ #
    # Indexing
    # ------------------------------------------------------------------ #

    def _build_index(self) -> None:
        """Build a flat id → child dict for O(1) lookups."""
        for record in self.records:
            for section in record.get("sections", []):
                for child in section.get("children", []):
                    child_id = child.get("id")
                    if child_id:
                        self._child_index[child_id] = child

    # ------------------------------------------------------------------ #
    # Linking
    # ------------------------------------------------------------------ #

    def _link_nearby_assets(self) -> None:
        """
        For every child that has nearby_content_ids,
        append its asset onto each referenced child node.
        """
        for record in self.records:
            for section in record.get("sections", []):
                for child in section.get("children", []):
                    nearby_ids = child.get("nearby_content_ids")
                    asset = child.get("asset")

                    if not nearby_ids or asset is None:
                        continue

                    self._attach_asset_to_nearby(nearby_ids, asset)

    def _attach_asset_to_nearby(
        self, nearby_ids: list[str], asset: object
    ) -> None:
        """Look up each nearby id and append the asset onto it."""
        for content_id in nearby_ids:
            target = self._child_index.get(content_id)
            if target is None:
                print(f":warning:  nearby_content_id not found: {content_id}")
                continue

            print(f":link: Linking asset to child id: {content_id}")
            target.setdefault("asset", [])

            # Avoid duplicate appends if run multiple times
            if asset not in target["asset"]:
                target["asset"].append(asset)


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #

def main():
    linker = NearbyContentLinker(
        input_path="Class8th_CGBoard_Science_final_structured2.json",
        output_path="updated_hierarchy.json",
    )
    linker.run()


if __name__ == "__main__":
    main() 