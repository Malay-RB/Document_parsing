class PageNumberTracker:
    def __init__(self):
        self.offset = None

    def resolve(self, pdf_page, detected_printed):

        # Ignore absurd numbers
        if detected_printed is not None:
            if detected_printed <= 0 or detected_printed > 2000:
                print(f":no_entry_sign: Ignoring absurd page number {detected_printed}")
                detected_printed = None

        # Lock offset on first valid detection
        if detected_printed is not None and self.offset is None:
            self.offset = detected_printed - pdf_page
            print(f":triangular_ruler: Pagination Offset Locked: {self.offset}")
            return detected_printed

        # If offset known
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

        return None