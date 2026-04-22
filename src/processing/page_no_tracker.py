class PageNumberTracker:
    def __init__(self):
        self.current_streak = []
        self.best_streak = []
        self.min_streak = 4
        self.max_ocr_error = 1  # ✅ Single parameter: tolerate ±1 OCR mistake per page

    def process(self, pdf_page, detected_printed):
        print(f"[Tracker] PDF page {pdf_page} → detected: {detected_printed}")
        
        # Filter noise
        if detected_printed is not None:
            if detected_printed <= 0 or detected_printed > 2000:
                print(f"🚫 Ignoring invalid value: {detected_printed}")
                detected_printed = None
        
        if detected_printed is None:
            return  # Skip missing numbers, don't break streak
        
        if not self.current_streak:
            # Start new streak
            self.current_streak.append((pdf_page, detected_printed))
            print(f"[STREAK] Started: PDF {pdf_page} → Printed {detected_printed}")
        else:
            # Check if this page continues the streak
            first_pdf, first_printed = self.current_streak[0]
            
            # ✅ What SHOULD the printed number be based on PDF progression?
            expected_printed = first_printed + (pdf_page - first_pdf)
            
            # ✅ How far off is it?
            error = abs(detected_printed - expected_printed)
            
            if error <= self.max_ocr_error:
                # ✅ Within tolerance - add to streak
                self.current_streak.append((pdf_page, detected_printed))
                print(f"[STREAK] Growing: PDF {pdf_page} → Printed {detected_printed} (error: {error})")
            else:
                # ❌ Too far off - save current streak and restart
                print(f"[BREAK] PDF {pdf_page}: expected {expected_printed}, got {detected_printed} (error: {error})")
                
                if len(self.current_streak) > len(self.best_streak):
                    self.best_streak = self.current_streak.copy()
                    print(f"  → New best streak: {len(self.best_streak)} pages")
                
                self.current_streak = [(pdf_page, detected_printed)]
                print(f"[STREAK] Restarted from PDF {pdf_page}")
        
        # Continuously update best
        if len(self.current_streak) > len(self.best_streak):
            self.best_streak = self.current_streak.copy()

    def finalize(self):
        # Final check
        if len(self.current_streak) > len(self.best_streak):
            self.best_streak = self.current_streak.copy()
        
        if len(self.best_streak) < self.min_streak:
            print(f"❌ No strong streak found (best: {len(self.best_streak)}, need: {self.min_streak})")
            return None
        
        # Calculate offset from best streak
        offsets = [printed - pdf for pdf, printed in self.best_streak]
        avg_offset = sum(offsets) / len(offsets)
        offset = round(avg_offset)
        
        # Validation: Check if offset is consistent
        offset_variance = max(offsets) - min(offsets)
        
        print(f"\n🔒 FINAL LOCK")
        print(f"[BEST STREAK]: {len(self.best_streak)} pages")
        print(f"[RANGE]: PDF {self.best_streak[0][0]}-{self.best_streak[-1][0]}")
        print(f"[FIRST 3]: {self.best_streak[:3]}")
        print(f"[LAST 3]: {self.best_streak[-3:]}")
        print(f"[OFFSET]: {offset} (variance: {offset_variance})")
        
        if offset_variance > 2:
            print(f"⚠️  WARNING: High offset variance ({offset_variance}). Streak may be unreliable.")
        
        return offset