class PageNumberTracker:
    def __init__(self):
        self.offset = None

        # NEW: streak tracking
        self.current_streak = []
        self.best_streak = []

        self.min_streak = 4  # tune this (3–5 recommended)

    def is_locked(self):
        return self.offset is not None and len(self.best_streak) >= self.min_streak

    def resolve(self, pdf_page, detected_printed):
        print(f"[Tracker] Input detected: {detected_printed}")  # :white_check_mark: HERE

        # Ignore absurd numbers
        if detected_printed is not None:
            if detected_printed <= 0 or detected_printed > 2000:
                print(f":no_entry_sign: Ignoring absurd page number {detected_printed}")
                detected_printed = None

        # ================================
        # :lock: If offset already locked → use it
        # ================================
        if self.offset is not None:
            expected = pdf_page + self.offset

            if detected_printed is not None:
                if detected_printed == expected:
                    return detected_printed
                else:
                    print(
                        f":warning: Suspicious detection {detected_printed}, expected {expected}. Using inferred."
                    )

            return expected

        # ================================
        # :brain: Build streak (core logic)
        # ================================
        if detected_printed is not None:

            if not self.current_streak:
                self.current_streak.append((pdf_page, detected_printed))
            else:
                _, last_printed = self.current_streak[-1]

                # Check sequential consistency
                if abs(detected_printed - (last_printed + 1)) <= 1:
                    self.current_streak.append((pdf_page, detected_printed))
                else:
                    # streak break → update best
                    if len(self.current_streak) > len(self.best_streak):
                        self.best_streak = self.current_streak

                    # start new streak
                    self.current_streak = [(pdf_page, detected_printed)]

        # Always keep best updated
        if len(self.current_streak) > len(self.best_streak):
            self.best_streak = self.current_streak

        # ================================
        # :closed_lock_with_key: Lock offset ONLY when confident
        # ================================
        if len(self.best_streak) >= self.min_streak:
            first_pdf, first_printed = self.best_streak[0]
            self.offset = first_printed - first_pdf

            print(f":triangular_ruler: Offset Locked from streak: {self.offset}")

            return pdf_page + self.offset

        return detected_printed if detected_printed is not None else pdf_page