class LayoutEngine:

    # receives the layout_predictor model
    def __init__(self, predictor):
        self.predictor = predictor

    # surya layout detection model expects list of images but we pass a single image so in order to read a single image we use [0] as index
    def detect(self, image):

        layout = self.predictor([image])[0]

        # returns coordinates, label, confidence
        return layout.bboxes
