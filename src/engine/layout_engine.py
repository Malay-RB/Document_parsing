class LayoutEngine:

    def __init__(self, predictor):
        self.predictor = predictor


    def detect(self, image):

        layout = self.predictor([image])[0]

        return layout.bboxes
