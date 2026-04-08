class PageNumberTracker:
    def __init__(self):
        self.current_streak = []
        self.best_streak = []
        self.min_streak = 4

    def process(self, pdf_page, detected_printed):
        print(f"[Tracker] Input detected: {detected_printed}")

        # Filter noise
        if detected_printed is not None:
            if detected_printed <= 0 or detected_printed > 2000:
                print(f":no_entry_sign: Ignoring {detected_printed}")
                detected_printed = None

        if detected_printed is None:
            return

        if not self.current_streak:
            self.current_streak.append((pdf_page, detected_printed))
            print(f"[STREAK] Started: {[detected_printed]}")
        else:
            _, last = self.current_streak[-1]

            if abs(detected_printed - (last + 1)) <= 1:
                self.current_streak.append((pdf_page, detected_printed))
                print(f"[STREAK] Growing: {[p for _, p in self.current_streak]}")
            else:
                print(f"[BREAK] at pdf={pdf_page}, val={detected_printed}")

                if len(self.current_streak) > len(self.best_streak):
                    self.best_streak = self.current_streak

                self.current_streak = [(pdf_page, detected_printed)]
                print(f"[STREAK] Restarted: {[detected_printed]}")

        if len(self.current_streak) > len(self.best_streak):
            self.best_streak = self.current_streak

    def finalize(self):
        if len(self.best_streak) < self.min_streak:
            print("❌ No strong streak found")
            return None

        first_pdf, first_printed = self.best_streak[0]
        offset = first_printed - first_pdf

        print(f"\n🔒 FINAL LOCK")
        print(f"[BEST STREAK]: {[p for _, p in self.best_streak]}")
        print(f"[OFFSET]: {offset}")

        return offset